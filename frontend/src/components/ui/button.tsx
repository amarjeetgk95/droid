import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-[4px] text-xs font-semibold whitespace-nowrap transition-colors outline-none focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-45 aria-invalid:border-destructive aria-invalid:ring-destructive/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-[#2a6fc0] active:bg-[#245fa5]",
        destructive:
          "bg-destructive text-white hover:bg-[#d94a2b] focus-visible:ring-destructive/20",
        buy: "bg-primary text-white hover:bg-[#2a6fc0] active:bg-[#245fa5]",
        sell: "bg-[#eb5b3c] text-white hover:bg-[#d94a2b] active:bg-[#c23d20]",
        outline:
          "border border-border bg-background shadow-xs hover:bg-[#f7f7f7] hover:border-primary/50 text-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-[#ebebeb]",
        ghost:
          "hover:bg-[#f7f7f7] hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-[34px] px-3.5 py-1.5 has-[>svg]:px-3",
        xs: "h-6 gap-1 rounded-[2px] px-2 text-[11px] has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-[28px] gap-1.5 rounded-[3px] px-2.5 text-[11.5px] has-[>svg]:px-2",
        lg: "h-[38px] rounded-[4px] px-5 has-[>svg]:px-4 text-sm",
        icon: "size-[34px]",
        "icon-xs": "size-6 rounded-[2px] [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-[28px] rounded-[3px]",
        "icon-lg": "size-[38px] rounded-[4px]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
