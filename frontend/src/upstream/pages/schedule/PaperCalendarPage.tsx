import { useState } from "react"
import { CalendarTabPage } from "./calendar-tab-page"

export function PaperCalendarPage() {
  const [currentDate, setCurrentDate] = useState(new Date())
  return <CalendarTabPage events={[]} onEventClick={() => {}} currentDate={currentDate} onMonthChange={setCurrentDate} />
}
