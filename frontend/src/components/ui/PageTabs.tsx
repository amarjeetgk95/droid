"use client"

import * as React from "react"
import { useRouter, useSearchParams, usePathname } from "next/navigation"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

export interface PageTabItem {
  id: string
  label: string
  icon?: React.ComponentType<{ className?: string }>
  badge?: string | number
  badgeClassName?: string
  content?: React.ReactNode
}

export interface PageTabsProps {
  tabs: PageTabItem[]
  defaultTab?: string
  activeTab?: string
  onTabChange?: (tabId: string) => void
  syncWithUrl?: boolean
  queryParam?: string
  className?: string
  listClassName?: string
  children?: React.ReactNode
}

export function PageTabs({
  tabs,
  defaultTab,
  activeTab: controlledActiveTab,
  onTabChange,
  syncWithUrl = false,
  queryParam = "tab",
  className,
  listClassName,
  children,
}: PageTabsProps) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const urlTab = syncWithUrl ? searchParams.get(queryParam) : null
  const initialTab = controlledActiveTab ?? urlTab ?? defaultTab ?? tabs[0]?.id

  const [internalTab, setInternalTab] = React.useState(initialTab)
  const currentTab = controlledActiveTab ?? (syncWithUrl && urlTab ? urlTab : internalTab)

  const handleValueChange = React.useCallback(
    (newTab: string) => {
      setInternalTab(newTab)
      onTabChange?.(newTab)

      if (syncWithUrl && pathname) {
        const params = new URLSearchParams(searchParams.toString())
        params.set(queryParam, newTab)
        router.replace(`${pathname}?${params.toString()}`, { scroll: false })
      }
    },
    [onTabChange, syncWithUrl, pathname, searchParams, queryParam, router]
  )

  return (
    <Tabs
      value={currentTab}
      onValueChange={handleValueChange}
      className={cn("w-full space-y-4", className)}
    >
      <div className="overflow-x-auto pb-1 scrollbar-none">
        <TabsList
          className={cn(
            "h-9 p-0.5 bg-secondary/60 border border-border rounded-lg inline-flex items-center gap-1 min-w-full sm:min-w-0",
            listClassName
          )}
        >
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <TabsTrigger
                key={tab.id}
                value={tab.id}
                className="px-3 py-1 text-xs font-semibold rounded-md gap-1.5 cursor-pointer data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-xs transition-all select-none"
              >
                {Icon && <Icon className="w-3.5 h-3.5 shrink-0" />}
                <span>{tab.label}</span>
                {tab.badge !== undefined && tab.badge !== null && (
                  <span
                    className={cn(
                      "ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold leading-tight",
                      tab.badgeClassName || "bg-primary/10 text-primary"
                    )}
                  >
                    {tab.badge}
                  </span>
                )}
              </TabsTrigger>
            )
          })}
        </TabsList>
      </div>

      {tabs.map((tab) =>
        tab.content ? (
          <TabsContent key={tab.id} value={tab.id} className="mt-0 focus-visible:outline-none">
            {tab.content}
          </TabsContent>
        ) : null
      )}

      {children}
    </Tabs>
  )
}
