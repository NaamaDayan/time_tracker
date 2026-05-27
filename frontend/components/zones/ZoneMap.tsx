"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Circle,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  Tooltip,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import type { ActivityType, GpsZone, GpsZoneCreateInput, GpsZoneUpdateInput, ZoneCategory } from "@/lib/types";
import { useZones } from "@/hooks/useZones";
import { AddressSearch } from "./AddressSearch";
import { ZonePopover } from "./ZonePopover";
import styles from "./ZoneMap.module.css";

const CATEGORY_COLORS: Record<ZoneCategory, string> = {
  home: "#93c5fd",
  work: "#c4b5fd",
  gym: "#86efac",
  family: "#fde047",
  social: "#f9a8d4",
  transit: "#9ca3af",
  other: "#cbd5e1",
};

const DEFAULT_CENTER: [number, number] = [32.08, 34.78];
const DEFAULT_ZOOM = 13;

const markerIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

interface AddPopoverState {
  lat: number;
  lon: number;
}

interface ZoneMapProps {
  activityTypes: ActivityType[];
}

function MapDblClickHandler({ onMapDblClick }: { onMapDblClick: (lat: number, lon: number) => void }) {
  useMapEvents({
    dblclick(e) {
      L.DomEvent.stopPropagation(e.originalEvent);
      onMapDblClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

export function ZoneMap({ activityTypes: initialActivityTypes }: ZoneMapProps) {
  const { zones, loading, addZone, editZone, removeZone } = useZones();
  const [addPopover, setAddPopover] = useState<AddPopoverState | null>(null);
  const [editingZone, setEditingZone] = useState<GpsZone | null>(null);
  const [activityTypes, setActivityTypes] = useState(initialActivityTypes);
  const mapRef = useRef<L.Map | null>(null);

  const bounds = useMemo(() => {
    if (zones.length === 0) return null;
    const group = L.latLngBounds(zones.map((z) => [z.lat, z.lon] as [number, number]));
    return group;
  }, [zones]);

  useEffect(() => {
    if (mapRef.current && bounds) {
      mapRef.current.fitBounds(bounds, { padding: [50, 50] });
    }
  }, [bounds]);

  const handleMapDblClick = (lat: number, lon: number) => {
    setEditingZone(null);
    setAddPopover({ lat, lon });
  };

  const handleAddressSelect = (lat: number, lon: number) => {
    setEditingZone(null);
    setAddPopover({ lat, lon });
    if (mapRef.current) {
      mapRef.current.setView([lat, lon], 16);
    }
  };

  const handleCreateZone = async (body: GpsZoneCreateInput | GpsZoneUpdateInput) => {
    await addZone(body as GpsZoneCreateInput);
    setAddPopover(null);
  };

  const handleUpdateZone = async (body: GpsZoneCreateInput | GpsZoneUpdateInput) => {
    if (!editingZone) return;
    await editZone(editingZone.id, body as GpsZoneUpdateInput);
    setEditingZone(null);
  };

  const handleDeleteZone = async () => {
    if (!editingZone) return;
    await removeZone(editingZone.id);
    setEditingZone(null);
  };

  const handleActivityTypeCreated = (atype: ActivityType) => {
    setActivityTypes((prev) => {
      if (prev.some((t) => t.slug === atype.slug)) return prev;
      return [...prev, atype].sort((a, b) => a.label.localeCompare(b.label));
    });
  };

  if (loading) {
    return <div className={styles.loading}>Loading zones...</div>;
  }

  return (
    <div className={styles.container}>
      <AddressSearch onSelect={handleAddressSelect} />
      <MapContainer
        center={bounds ? undefined : DEFAULT_CENTER}
        bounds={bounds ?? undefined}
        zoom={bounds ? undefined : DEFAULT_ZOOM}
        className={styles.map}
        ref={mapRef}
        doubleClickZoom={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapDblClickHandler onMapDblClick={handleMapDblClick} />

        {zones.map((zone) => (
          <Circle
            key={zone.id}
            center={[zone.lat, zone.lon]}
            radius={zone.radius_meters}
            pathOptions={{
              color: CATEGORY_COLORS[zone.category] ?? CATEGORY_COLORS.other,
              fillColor: CATEGORY_COLORS[zone.category] ?? CATEGORY_COLORS.other,
              fillOpacity: 0.25,
              weight: 2,
            }}
            eventHandlers={{
              click: (e) => {
                L.DomEvent.stopPropagation(e);
                setAddPopover(null);
                setEditingZone(zone);
              },
            }}
          >
            <Tooltip permanent direction="center" className={styles.zoneLabel}>
              {zone.name}
            </Tooltip>
          </Circle>
        ))}

        {zones.map((zone) => (
          <Marker
            key={`marker-${zone.id}`}
            position={[zone.lat, zone.lon]}
            icon={markerIcon}
            eventHandlers={{
              click: (e) => {
                L.DomEvent.stopPropagation(e);
                setAddPopover(null);
                setEditingZone(zone);
              },
            }}
          />
        ))}

        {addPopover && (
          <Popup
            position={[addPopover.lat, addPopover.lon]}
            closeButton={false}
            className={styles.popup}
            eventHandlers={{ remove: () => setAddPopover(null) }}
          >
            <ZonePopover
              lat={addPopover.lat}
              lon={addPopover.lon}
              activityTypes={activityTypes}
              onSave={handleCreateZone}
              onClose={() => setAddPopover(null)}
              onActivityTypeCreated={handleActivityTypeCreated}
            />
          </Popup>
        )}

        {editingZone && (
          <Popup
            position={[editingZone.lat, editingZone.lon]}
            closeButton={false}
            className={styles.popup}
            eventHandlers={{ remove: () => setEditingZone(null) }}
          >
            <ZonePopover
              lat={editingZone.lat}
              lon={editingZone.lon}
              zone={editingZone}
              activityTypes={activityTypes}
              onSave={handleUpdateZone}
              onDelete={handleDeleteZone}
              onClose={() => setEditingZone(null)}
              onActivityTypeCreated={handleActivityTypeCreated}
            />
          </Popup>
        )}
      </MapContainer>
    </div>
  );
}
