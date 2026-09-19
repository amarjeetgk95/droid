import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

/* Single badge primitive. The union of variant names covers both the legacy
   shared kit (success/danger/warning/info/purple/neutral/outline/bull/bear)
   and the radix kit aliases (default/secondary/destructive/ghost/link). */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 font-medium rounded-full border transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        neutral: "bg-muted text-ink-2 border-border",
        outline: "bg-transparent text-ink-2 border-border-strong",
        success: "bg-up-wash text-up-strong border-up-line",
        danger: "bg-down-wash text-down-strong border-down-line",
        destructive: "bg-down-wash text-down-strong border-down-line",
        warning: "bg-warn-wash text-warn-strong border-warn-line",
        info: "bg-accent-wash text-primary border-accent-line",
        default: "bg-accent-wash text-primary border-accent-line",
        purple: "bg-accent-wash text-primary border-accent-line",
        bull: "bg-up-wash text-up-strong border-up-line font-bold",
        bear: "bg-down-wash text-down-strong border-down-line font-bold",
        secondary: "bg-muted text-muted-foreground border-border",
        ghost: "border-transparent bg-transparent text-ink-2",
        link: "border-transparent bg-transparent text-primary underline-offset-4 hover:underline",
      },
      size: {
        xs: "text-[11px] px-2 py-0.5 tracking-normal",
        sm: "text-xs px-2.5 py-0.5 tracking-normal",
        md: "text-[13px] px-3 py-1 tracking-normal",
      },
    },
    defaultVariants: {
      variant: "neutral",
      size: "sm",
    },
  }
)

export type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>
export type BadgeSize = NonNullable<VariantProps<typeof badgeVariants>["size"]>

const dotColors: Record<BadgeVariant, string> = {
  neutral: "bg-ink-4",
  outline: "bg-ink-4",
  success: "bg-up",
  danger: "bg-down",
  destructive: "bg-down",
  warning: "bg-warn",
  info: "bg-primary",
  default: "bg-primary",
  purple: "bg-primary",
  bull: "bg-up",
  bear: "bg-down",
  secondary: "bg-ink-4",
  ghost: "bg-ink-4",
  link: "bg-primary",
}

type BadgeProps = Omit<React.ComponentProps<"span">, "onClick"> &
  VariantProps<typeof badgeVariants> & {
    asChild?: boolean
    dot?: boolean
    onClick?: () => void
  }

function Badge({
  className,
  variant,
  size,
  asChild = false,
  dot = false,
  children,
  onClick,
  ...props
}: BadgeProps) {
  const Comp = asChild ? Slot.Root : "span"
  const v = (variant ?? "neutral") as BadgeVariant

  return (
    <Comp
      data-slot="badge"
      data-variant={v}
      onClick={onClick}
      className={cn(
        badgeVariants({ variant: v, size }),
        onClick && "cursor-pointer hover:opacity-80",
        className
      )}
      {...props}
    >
      {asChild ? (
        children
      ) : (
        <>
          {dot && (
            <span
              aria-hidden="true"
              className={cn(
                "w-1.5 h-1.5 rounded-full inline-block animate-pulse motion-reduce:animate-none",
                dotColors[v]
              )}
            />
          )}
          {children}
        </>
      )}
    </Comp>
  )
}

export { Badge, badgeVariants }
