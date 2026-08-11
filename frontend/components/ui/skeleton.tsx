import { cn } from "@/lib/utils"

/** 로딩 자리표시자(shadcn 스타일). 무거운 분석(path_ranking ~수초) 로드 중 뼈대를 보인다. */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  )
}

export { Skeleton }
