import * as React from "react"

import { cn } from "@/lib/utils"

type CardGlow = "cyan" | "emerald" | "indigo" | "rose" | "amber" | "none"

/* Legacy `glow` tones (prop-based API) map onto the semantic families —
   border emphasis only, the design system has no coloured shadows. */
const glowStyles: Record<CardGlow, string> = {
  none: "",
  cyan: "border-primary",
  emerald: "border-up-line",
  indigo: "border-accent-line",
  rose: "border-down-line",
  amber: "border-warn-line",
}

type CardProps = Omit<React.ComponentProps<"div">, "title"> & {
  /** Prop-based API (legacy shared kit) — renders a titled panel. */
  title?: React.ReactNode
  subtitle?: React.ReactNode
  headerAction?: React.ReactNode
  footer?: React.ReactNode
  noPadding?: boolean
  glow?: CardGlow
}

function Card({
  className,
  title,
  subtitle,
  headerAction,
  footer,
  noPadding,
  glow,
  children,
  ...props
}: CardProps) {
  // Presence of any prop-based prop selects the legacy panel rendering;
  // otherwise the compound API (CardHeader/CardContent/... below) is used.
  const propMode =
    title !== undefined ||
    subtitle !== undefined ||
    headerAction !== undefined ||
    footer !== undefined ||
    noPadding !== undefined ||
    glow !== undefined

  if (propMode) {
    return (
      <div
        className={cn(
          "relative rounded-lg border border-border bg-card text-foreground transition-all duration-200",
          glowStyles[glow ?? "none"],
          className
        )}
        {...props}
      >
        {(title || subtitle || headerAction) && (
          <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle bg-surface-subtle">
            <div>
              {title && <div className="text-sm font-semibold tracking-wide text-foreground">{title}</div>}
              {subtitle && <div className="text-xs text-ink-3 mt-0.5">{subtitle}</div>}
            </div>
            {headerAction && <div className="flex items-center gap-2">{headerAction}</div>}
          </div>
        )}
        <div className={noPadding ? "" : "p-4"}>{children}</div>
        {footer && (
          <div className="px-4 py-2.5 border-t border-border-subtle bg-surface-subtle text-xs text-ink-3">
            {footer}
          </div>
        )}
      </div>
    )
  }

  return (
    <div
      data-slot="card"
      className={cn(
        "flex flex-col gap-4 rounded-[4px] border border-border bg-card py-4 text-card-foreground shadow-[0_1px_2px_rgba(0,0,0,0.04)]",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start gap-1.5 px-4 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-3",
        className
      )}
      {...props}
    />
  )
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn("leading-none font-semibold text-[13px] text-foreground tracking-tight", className)}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-xs text-muted-foreground", className)}
      {...props}
    />
  )
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn(
        "col-start-2 row-span-2 row-start-1 self-start justify-self-end",
        className
      )}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("px-4", className)}
      {...props}
    />
  )
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn("flex items-center px-4 [.border-t]:pt-3", className)}
      {...props}
    />
  )
}

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
}

export type { CardProps, CardGlow }
