"use client";

import type React from "react";
import type {
  DateSelectArg,
  DatesSetArg,
  EventClickArg,
  EventContentArg,
  EventDropArg,
  EventInput,
  EventMountArg,
} from "@fullcalendar/core";
import type { EventResizeDoneArg } from "@fullcalendar/interaction";
import interactionPlugin from "@fullcalendar/interaction";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import { useCallback, useRef } from "react";
import styles from "./WeekCalendar.module.css";

export interface CalendarEventChange {
  id: string;
  start: Date;
  end: Date;
  allDay: boolean;
}

interface WeekCalendarProps {
  timezone: string;
  events: EventInput[];
  onDatesChange: (from: Date, to: Date) => void;
  onSelectRange?: (start: Date, end: Date, allDay: boolean) => void;
  onEventClick?: (eventId: string, anchor: DOMRect) => void;
  onEventChange?: (change: CalendarEventChange) => void;
  renderEventContent?: (arg: EventContentArg) => React.ReactNode;
  highlightEventId?: string | null;
}

export function WeekCalendar({
  timezone,
  events,
  onDatesChange,
  onSelectRange,
  onEventClick,
  onEventChange,
  renderEventContent,
  highlightEventId,
}: WeekCalendarProps) {
  const calendarRef = useRef<FullCalendar>(null);

  const handleDatesSet = useCallback(
    (arg: DatesSetArg) => {
      onDatesChange(arg.start, arg.end);
    },
    [onDatesChange]
  );

  const handleSelect = useCallback(
    (arg: DateSelectArg) => {
      arg.view.calendar.unselect();
      onSelectRange?.(arg.start, arg.end, arg.allDay);
    },
    [onSelectRange]
  );

  const handleEventClick = useCallback(
    (arg: EventClickArg) => {
      arg.jsEvent.preventDefault();
      if (arg.event.id && arg.el) {
        onEventClick?.(arg.event.id, arg.el.getBoundingClientRect());
      }
    },
    [onEventClick]
  );

  const handleEventDidMount = useCallback(
    (arg: EventMountArg) => {
      if (arg.event.id) {
        arg.el.dataset.eventId = arg.event.id;
      }
      if (highlightEventId && arg.event.id === highlightEventId) {
        arg.el.classList.add("fc-event-review-highlight");
      }
    },
    [highlightEventId]
  );

  const emitEventChange = useCallback(
    (id: string, start: Date | null, end: Date | null, allDay: boolean) => {
      if (!start || !end) return;
      onEventChange?.({ id, start, end, allDay });
    },
    [onEventChange]
  );

  const handleEventDrop = useCallback(
    (arg: EventDropArg) => {
      emitEventChange(arg.event.id, arg.event.start, arg.event.end, arg.event.allDay);
    },
    [emitEventChange]
  );

  const handleEventResize = useCallback(
    (arg: EventResizeDoneArg) => {
      emitEventChange(arg.event.id, arg.event.start, arg.event.end, arg.event.allDay);
    },
    [emitEventChange]
  );

  return (
    <div className={styles.wrap}>
      <p className={styles.hint}>
        Drag on the grid to add an event. Click an event to view or edit. Manual events can be
        dragged to reschedule.
      </p>
      <FullCalendar
        ref={calendarRef}
        plugins={[timeGridPlugin, interactionPlugin]}
        initialView="timeGridWeek"
        firstDay={0}
        timeZone={timezone}
        headerToolbar={{
          left: "prev,next today",
          center: "title",
          right: "",
        }}
        height={960}
        expandRows
        slotMinTime="00:00:00"
        slotMaxTime="24:00:00"
        slotDuration="00:30:00"
        slotLabelInterval="01:00:00"
        allDaySlot
        allDayText="All day"
        nowIndicator
        scrollTime="08:00:00"
        events={events}
        datesSet={handleDatesSet}
        selectable={Boolean(onSelectRange)}
        selectMirror
        unselectAuto
        editable={Boolean(onEventChange)}
        eventStartEditable={Boolean(onEventChange)}
        eventDurationEditable={Boolean(onEventChange)}
        eventResizableFromStart
        slotEventOverlap={false}
        eventMinHeight={22}
        eventShortHeight={28}
        dayMaxEvents={4}
        eventMaxStack={4}
        eventDisplay="block"
        select={handleSelect}
        eventClick={handleEventClick}
        eventDrop={handleEventDrop}
        eventResize={handleEventResize}
        eventContent={renderEventContent}
        eventDidMount={handleEventDidMount}
      />
    </div>
  );
}
