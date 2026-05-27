"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./AddressSearch.module.css";

interface PhotonFeature {
  geometry: { coordinates: [number, number] };
  properties: {
    name?: string;
    street?: string;
    housenumber?: string;
    city?: string;
    state?: string;
    country?: string;
    osm_id: number;
  };
}

interface PhotonResponse {
  features?: PhotonFeature[];
}

function formatResult(props: PhotonFeature["properties"]): string {
  const parts: string[] = [];
  if (props.name) parts.push(props.name);
  if (props.street) {
    const street = props.housenumber
      ? `${props.street} ${props.housenumber}`
      : props.street;
    if (!parts.includes(street) && street !== props.name) parts.push(street);
  } else if (props.housenumber) {
    parts.push(props.housenumber);
  }
  if (props.city && !parts.includes(props.city)) parts.push(props.city);
  if (props.country && !parts.includes(props.country)) parts.push(props.country);
  return parts.join(", ");
}

interface AddressSearchProps {
  onSelect: (lat: number, lon: number, displayName: string) => void;
}

export function AddressSearch({ onSelect }: AddressSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<
    { key: string; label: string; lat: number; lon: number }[]
  >([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const search = useCallback(async (q: string) => {
    if (q.length < 2) {
      setResults([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        q,
        limit: "8",
      });
      const res = await fetch(`https://photon.komoot.io/api/?${params}`);
      if (!res.ok) {
        setResults([]);
        setError("Address search failed. Try a shorter query.");
        setIsOpen(false);
        return;
      }
      const data: PhotonResponse = await res.json();
      const features = data.features ?? [];
      const items = features
        .map((f, i) => {
          const label = formatResult(f.properties);
          return {
            key: `${f.properties.osm_id}-${i}`,
            label,
            lon: f.geometry.coordinates[0],
            lat: f.geometry.coordinates[1],
          };
        })
        .filter((item) => item.label.length > 0);
      setResults(items);
      setIsOpen(items.length > 0);
      if (items.length === 0) {
        setError("No results found.");
      }
    } catch {
      setResults([]);
      setError("Could not reach address search.");
      setIsOpen(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.length < 2) {
      setResults([]);
      setIsOpen(false);
      setError(null);
      return;
    }
    debounceRef.current = setTimeout(() => search(query), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, search]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (item: { lat: number; lon: number; label: string }) => {
    setQuery(item.label);
    setIsOpen(false);
    setResults([]);
    setError(null);
    onSelect(item.lat, item.lon, item.label);
  };

  return (
    <div className={styles.container} ref={containerRef}>
      <div className={styles.inputWrapper}>
        <svg
          className={styles.searchIcon}
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          type="text"
          className={styles.input}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (results.length > 0) setIsOpen(true);
          }}
          placeholder="Search address..."
        />
        {loading && <span className={styles.spinner} />}
      </div>
      {isOpen && results.length > 0 && (
        <ul className={styles.dropdown}>
          {results.map((r) => (
            <li key={r.key}>
              <button
                type="button"
                className={styles.resultItem}
                onClick={() => handleSelect(r)}
              >
                {r.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      {!loading && error && query.length >= 2 && (
        <p className={styles.hint}>{error}</p>
      )}
    </div>
  );
}
