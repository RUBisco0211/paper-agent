import * as React from "react"
import { cn } from "cn"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-(--control-height-lg) w-full min-w-0 rounded-md border border-input bg-(--control-input-bg) px-(--button-padding-md) py-1 text-base shadow-xs transition-[color,box-shadow] duration-(--motion-duration-hover) ease-(--motion-ease-standard) outline-none selection:bg-primary selection:text-primary-foreground file:inline-flex file:h-(--control-height-sm) file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-(--disabled-opacity) md:text-sm",
        "focus-visible:border-ring focus-visible:ring-(length:--focus-ring-width) focus-visible:ring-(--focus-ring-color)",
        "aria-invalid:border-destructive aria-invalid:ring-(--destructive-ring)",
        className
      )}
      {...props}
    />
  )
}

export { Input }
