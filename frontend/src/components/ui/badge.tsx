import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-[3px] border border-transparent px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap transition-colors focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring aria-invalid:border-destructive aria-invalid:ring-destructive/20 [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        default: "bg-[#edf4fc] text-[#387ed1] border-[rgba(56,126,209,0.25)] [a&]:hover:bg-[#e0eefc]",
        secondary:
          "bg-[#f4f4f4] text-[#666666] border-border [a&]:hover:bg-[#ebebeb]",
        destructive:
          "bg-[#fdf0ef] text-[#c62828] border-[rgba(223,81,76,0.25)] [a&]:hover:bg-[#fbdad7]",
        success:
          "bg-[#edf8ef] text-[#2e7d32] border-[rgba(76,175,80,0.25)] [a&]:hover:bg-[#d8f0dc]",
        outline:
          "border-border text-foreground bg-card [a&]:hover:bg-[#f7f7f7]",
        ghost: "[a&]:hover:bg-[#f7f7f7] hover:text-foreground",
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
