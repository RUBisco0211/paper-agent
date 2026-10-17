import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@upstream/lib/utils"
import { Slot } from "radix-ui"

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-(--control-gap-sm) overflow-hidden rounded-md border border-transparent px-2 py-0.5 text-label font-medium uppercase tracking-label whitespace-nowrap transition-[color,box-shadow] duration-(--motion-duration-hover) ease-(--motion-ease-standard) focus-visible:border-ring focus-visible:ring-(length:--focus-ring-width) focus-visible:ring-(--focus-ring-color) aria-invalid:border-destructive aria-invalid:ring-(--destructive-ring) [&>svg]:pointer-events-none [&>svg]:size-(--icon-size-xs)",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a&]:hover:bg-(--control-primary-hover-bg)",
        secondary:
          "bg-secondary text-secondary-foreground [a&]:hover:bg-(--control-secondary-hover-bg)",
        destructive:
          "bg-destructive text-destructive-foreground focus-visible:ring-(--destructive-ring) [a&]:hover:bg-(--destructive-solid-hover-bg)",
        outline:
          "border-border text-foreground [a&]:hover:bg-(--control-outline-hover-bg) [a&]:hover:text-accent-foreground",
        ghost: "[a&]:hover:bg-(--control-ghost-hover-bg) [a&]:hover:text-accent-foreground",
        success: "border-(--success-border) bg-(--success-subtle) text-success",
        warning: "border-(--warning-border) bg-(--warning-subtle) text-warning",
        link: "text-primary underline-offset-4 [a&]:hover:underline",
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
