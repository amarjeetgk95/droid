"use client"

import * as React from "react"
import { AlertCircle, RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"

export interface ErrorCardProps {
  title?: string
  message?: string
  mode?: "inline" | "banner" | "full-page"
  onRetry?: () => void
  isRetrying?: boolean
  className?: string
}

export function ErrorCard({
  title = "Data unavailable",
  message,
  mode = "inline",
  onRetry,
  isRetrying = false,
  className,
}: ErrorCardProps) {
  if (mode === "banner") {
    return (
      <div
        data-slot="error-banner"
        className={cn(
          "flex items-center justify-between gap-3 p-3 rounded-xl border border-destructive/30 bg-destructive/10 text-destructive text-xs",
          className
        )}
      >
        <div className="flex items-center gap-2 min-w-0">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <div className="truncate">
            <span className="font-semibold">{title}</span>
            {message && <span className="text-muted-foreground ml-1.5">— {message}</span>}
          </div>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            disabled={isRetrying}
            className="px-2.5 py-1 rounded-md bg-destructive/15 hover:bg-destructive/25 text-destructive font-semibold transition-colors cursor-pointer shrink-0 flex items-center gap-1 text-[11px]"
          >
            <RefreshCw className={cn("w-3 h-3", isRetrying && "animate-spin")} />
            <span>Retry</span>
          </button>
        )}
      </div>
    )
  }

  if (mode === "full-page") {
    return (
      <div
        data-slot="error-full-page"
        className={cn(
          "min-h-[380px] flex flex-col items-center justify-center p-8 bg-card border border-destructive/20 rounded-2xl text-center space-y-4 shadow-sm",
          className
        )}
      >
        <div className="w-12 h-12 rounded-full bg-destructive/10 text-destructive flex items-center justify-center mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <div className="space-y-1 max-w-sm">
          <h3 className="text-base font-bold text-foreground">{title}</h3>
          {message && <p className="text-xs text-muted-foreground leading-relaxed">{message}</p>}
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            disabled={isRetrying}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-all cursor-pointer shadow-xs disabled:opacity-50"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", isRetrying && "animate-spin")} />
            <span>Retry Connection</span>
          </button>
        )}
      </div>
    )
  }

  // Inline widget error
  return (
    <div
      data-slot="error-inline"
      className={cn(
        "bg-card border border-destructive/30 rounded-xl p-5 min-h-[160px] flex flex-col items-center justify-center text-center gap-2.5 shadow-2xs",
        className
      )}
    >
      <div className="p-2 rounded-lg bg-destructive/10 text-destructive">
        <AlertCircle className="w-5 h-5" />
      </div>
      <div className="space-y-0.5 max-w-xs">
        <p className="text-xs font-bold text-foreground">{title}</p>
        {message && <p className="text-[11px] text-muted-foreground">{message}</p>}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          disabled={isRetrying}
          className="mt-1 inline-flex items-center gap-1 px-3 py-1 rounded-md bg-secondary hover:bg-secondary/80 text-foreground text-xs font-semibold transition-colors cursor-pointer border border-border"
        >
          <RefreshCw className={cn("w-3 h-3", isRetrying && "animate-spin")} />
          <span>Retry</span>
        </button>
      )}
    </div>
  )
}
