import { format, parse } from "date-fns"
import { zhCN } from "date-fns/locale"
import { CalendarIcon } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"

type DatePickerProps = {
  value: string
  onChange: (value: string) => void
  className?: string
  placeholder?: string
}

function parseISODate(value: string): Date {
  return parse(value, "yyyy-MM-dd", new Date())
}

function toISODate(date: Date): string {
  return format(date, "yyyy-MM-dd")
}

export function DatePicker({
  value,
  onChange,
  className,
  placeholder = "Select date",
}: DatePickerProps) {
  const [open, setOpen] = useState(false)
  const selected = value ? parseISODate(value) : undefined

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "w-44 justify-start text-left font-normal",
            !value && "text-muted-foreground",
            className,
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4" />
          {selected
            ? format(selected, "yyyy-MM-dd", { locale: zhCN })
            : placeholder}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="end">
        <Calendar
          mode="single"
          selected={selected}
          defaultMonth={selected}
          locale={zhCN}
          onSelect={(date) => {
            if (date) {
              onChange(toISODate(date))
              setOpen(false)
            }
          }}
        />
      </PopoverContent>
    </Popover>
  )
}