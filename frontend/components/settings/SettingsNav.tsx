"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SETTINGS_NAV_ITEMS } from "@/lib/settingsNav";
import styles from "./SettingsNav.module.css";

export function SettingsNav() {
  const pathname = usePathname();

  return (
    <nav className={styles.nav} aria-label="Settings sections">
      <ul className={styles.list}>
        {SETTINGS_NAV_ITEMS.map(({ href, label }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <li key={href}>
              <Link
                href={href}
                className={active ? styles.linkActive : styles.link}
                aria-current={active ? "page" : undefined}
              >
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
