import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-[3px] border border-transparent px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap transition-colors focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring aria-invalid:border-destructive aria-invalid:ring-destructive/20 [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        default:
          "bg-accent-wash text-primary border-accent-line [a&]:hover:bg-primary/10",
        secondary:
          "bg-muted text-muted-foreground border-border [a&]:hover:bg-muted-strong",
        destructive:
          "bg-down-wash text-down border-down-line [a&]:hover:bg-down/10",
        success:
          "bg-up-wash text-up border-up-line [a&]:hover:bg-up/10",
        warning:
          "bg-warn-wash text-warn border-warn-line [a&]:hover:bg-warn/10",
        outline:
          "border-border text-foreground bg-card [a&]:hover:bg-muted",
        ghost: "[a&]:hover:bg-muted hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
