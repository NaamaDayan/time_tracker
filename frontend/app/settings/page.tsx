import Link from "next/link";
import { SETTINGS_NAV_ITEMS } from "@/lib/settingsNav";
import styles from "./settingsHome.module.css";

export const dynamic = "force-dynamic";

export default function SettingsPage() {
  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <h2>Overview</h2>
        <p className={styles.sub}>
          Choose a section from the sidebar, or pick one below.
        </p>
      </header>

      <ul className={styles.list}>
        {SETTINGS_NAV_ITEMS.map((section) => (
          <li key={section.href}>
            <Link href={section.href} className={styles.card}>
              <h3>{section.label}</h3>
              <p>{section.description}</p>
              <span className={styles.arrow}>Open →</span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
