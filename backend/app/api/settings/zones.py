import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import verify_api_key
from app.database import get_db
from app.models.gps_zone import GpsZone
from app.rules.zone_category_defaults import CATEGORY_DEFAULTS
from app.schemas.gps_zone import GpsZoneCreate, GpsZoneOut, GpsZoneUpdate

router = APIRouter(
    prefix="/api/v1/settings/zones",
    tags=["settings", "zones"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/", response_model=list[GpsZoneOut])
def list_zones(db: Session = Depends(get_db)) -> list[GpsZoneOut]:
    zones = (
        db.query(GpsZone)
        .filter(GpsZone.enabled.is_(True))
        .order_by(GpsZone.name)
        .all()
    )
    return [GpsZoneOut.model_validate(z) for z in zones]


@router.post("/", response_model=GpsZoneOut, status_code=status.HTTP_201_CREATED)
def create_zone(body: GpsZoneCreate, db: Session = Depends(get_db)) -> GpsZoneOut:
    existing = db.query(GpsZone).filter(GpsZone.name == body.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Zone with name '{body.name}' already exists",
        )

    activity_slug = body.activity_type_slug
    if activity_slug is None:
        activity_slug = CATEGORY_DEFAULTS.get(body.category)

    zone = GpsZone(
        name=body.name,
        category=body.category,
        activity_type_slug=activity_slug,
        lat=body.lat,
        lon=body.lon,
        radius_meters=body.radius_meters,
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return GpsZoneOut.model_validate(zone)


@router.patch("/{zone_id}", response_model=GpsZoneOut)
def update_zone(
    zone_id: uuid.UUID, body: GpsZoneUpdate, db: Session = Depends(get_db)
) -> GpsZoneOut:
    zone = db.query(GpsZone).filter(GpsZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(zone, field, value)

    if "category" in update_data and "activity_type_slug" not in update_data:
        zone.activity_type_slug = CATEGORY_DEFAULTS.get(zone.category)

    db.commit()
    db.refresh(zone)
    return GpsZoneOut.model_validate(zone)


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zone(zone_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    zone = db.query(GpsZone).filter(GpsZone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    db.delete(zone)
    db.commit()
