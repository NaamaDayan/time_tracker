import Link from "next/link";
import { SettingsNav } from "@/components/settings/SettingsNav";
import styles from "./settings.module.css";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <Link href="/" className={styles.backToApp}>
          &larr; Time Tracker
        </Link>
        <h1 className={styles.sidebarTitle}>Settings</h1>
        <SettingsNav />
      </aside>
      <div className={styles.content}>{children}</div>
    </div>
  );
}
