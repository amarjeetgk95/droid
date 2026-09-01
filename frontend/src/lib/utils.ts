import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Null-safe number formatting — never crashes on null/undefined/NaN. */
export function safeNum(value: number | null | undefined, fallback = "—", digits = 2): string {
  if (value === null || value === undefined) return fallback;
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return n.toFixed(digits);
}

/** Null-safe integer-ish formatting (volume, OI, counts). */
export function safeInt(value: number | null | undefined, fallback = "—"): string {
  if (value === null || value === undefined) return fallback;
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.round(n).toLocaleString();
}

/** Null-safe string rendering — never crashes on undefined. */
export function safeStr(value: string | null | undefined, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

/** Null-safe date/time rendering — avoids "Invalid Date". */
export function safeTime(value: string | null | undefined, fallback = "—"): string {
  if (!value) return fallback;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return fallback;
  return d.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });
}
