"use client";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

export function SkeletonBlock({
  variant = "card",
  count = 1,
  className,
}: {
  variant?: "card" | "row" | "tile" | "text" | "board";
  count?: number;
  className?: string;
}) {
  const items = Array.from({ length: count });

  if (variant === "board") {
    return (
      <div className={cn("grid grid-cols-1 gap-4 md:grid-cols-5", className)}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="space-y-3">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      className={cn(
        variant === "tile" && "grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4",
        variant === "row" && "space-y-2",
        variant === "card" && "space-y-3",
        variant === "text" && "space-y-2",
        className,
      )}
    >
      {items.map((_, i) => {
        if (variant === "tile") {
          return <Skeleton key={i} className="aspect-square w-full rounded-lg" />;
        }
        if (variant === "row") {
          return <Skeleton key={i} className="h-12 w-full rounded-lg" />;
        }
        if (variant === "text") {
          return <Skeleton key={i} className="h-4 w-full" />;
        }
        return <Skeleton key={i} className="h-28 w-full rounded-lg" />;
      })}
    </div>
  );
}
