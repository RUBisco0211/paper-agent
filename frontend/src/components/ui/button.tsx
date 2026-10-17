import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@upstream/lib/utils"
import { Slot } from "radix-ui"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-(--control-gap-lg) rounded-md text-ui font-medium whitespace-nowrap transition-all duration-(--motion-duration-hover) ease-(--motion-ease-standard) outline-none focus-visible:border-ring focus-visible:ring-(length:--focus-ring-width) focus-visible:ring-(--focus-ring-color) disabled:pointer-events-none disabled:opacity-(--disabled-opacity) aria-invalid:border-destructive aria-invalid:ring-(--destructive-ring) [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-(--icon-size-md)",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-(--control-primary-hover-bg)",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-(--destructive-solid-hover-bg) focus-visible:ring-(--destructive-ring)",
        outline:
          "border border-(--control-outline-border) bg-(--control-outline-bg) shadow-xs hover:bg-(--control-outline-hover-bg) hover:text-accent-foreground",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-(--control-secondary-hover-bg)",
        ghost:
          "hover:bg-(--control-ghost-hover-bg) hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-(--control-height-lg) px-(--button-padding-md) py-2 has-[>svg]:px-(--button-padding-xs)",
        xs: "h-(--control-height-xs) gap-(--control-gap-sm) rounded-md px-(--button-padding-xs) text-xs has-[>svg]:px-(--control-gap-md) [&_svg:not([class*='size-'])]:size-(--icon-size-xs)",
        sm: "h-(--control-height-md) gap-(--control-gap-md) rounded-md px-(--button-padding-sm) has-[>svg]:px-(--button-padding-xs)",
        lg: "h-(--control-height-xl) rounded-md px-(--button-padding-lg) has-[>svg]:px-(--button-padding-md)",
        icon: "size-(--control-height-lg)",
        "icon-xs": "size-(--control-height-xs) rounded-md [&_svg:not([class*='size-'])]:size-(--icon-size-xs)",
        "icon-sm": "size-(--control-height-md)",
        "icon-lg": "size-(--control-height-xl)",
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
