"use client";

import styles from "./Tabs.module.css";

export interface TabItem<T extends string> {
  id: T;
  label: string;
}

interface TabsProps<T extends string> {
  tabs: TabItem<T>[];
  active: T;
  onChange: (id: T) => void;
  variant?: "main" | "sub";
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  variant = "main",
}: TabsProps<T>) {
  return (
    <div className={variant === "main" ? styles.main : styles.sub} role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          className={active === tab.id ? styles.active : styles.tab}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
