import { useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent } from "react";
import { Button, Input } from "antd";
import { SendOutlined } from "@ant-design/icons";

const { TextArea } = Input;

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
}

const SUGGESTIONS = [
  { title: "Academic Calendar", prompt: "Give me the key academic calendar dates for this academic year." },
  { title: "Course Timetable", prompt: "Give me the information I need to understand my course timetable." },
  { title: "Admission Info", prompt: "Summarize the admission requirements for FTSM postgraduate programs." },
  { title: "Visa Renewal", prompt: "Explain the student visa renewal steps and required documents." },
  { title: "Campus Bus", prompt: "Give me the UKM campus bus route information relevant to students." },
  { title: "Staff Directory", prompt: "Give me information about FTSM academic staff and their expertise." },
  { title: "Registration", prompt: "Explain what I should prepare for course registration renewal." },
  { title: "Industrial Training", prompt: "Summarize the industrial training information and important contacts." },
  { title: "Facilities", prompt: "List the facilities and services available at FTSM." },
  { title: "Public Holidays", prompt: "Give me the Malaysian public holiday dates for this academic year." },
  { title: "Student Systems", prompt: "Explain the UKM student systems used for academic matters." },
  { title: "Exam Schedule", prompt: "Give me the final exam schedule information and what I should check." },
];

export default function Composer({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const [draggingSuggestions, setDraggingSuggestions] = useState(false);
  const suggestionsRef = useRef<HTMLDivElement>(null);
  const dragState = useRef({ pointerId: -1, startX: 0, scrollLeft: 0, moved: false });

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };

  const handleSuggestionsWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    const row = suggestionsRef.current;
    if (!row || row.scrollWidth <= row.clientWidth) return;
    const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
    if (!delta) return;
    event.preventDefault();
    row.scrollLeft += delta;
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    const row = suggestionsRef.current;
    if (!row) return;
    dragState.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      scrollLeft: row.scrollLeft,
      moved: false,
    };
    setDraggingSuggestions(true);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const row = suggestionsRef.current;
    const drag = dragState.current;
    if (!row || drag.pointerId !== event.pointerId) return;
    const distance = event.clientX - drag.startX;
    if (Math.abs(distance) > 4) {
      if (!drag.moved) {
        row.setPointerCapture(event.pointerId);
        drag.moved = true;
      }
      row.scrollLeft = drag.scrollLeft - distance;
    }
  };

  const stopDragging = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragState.current.pointerId !== event.pointerId) return;
    const row = suggestionsRef.current;
    if (row && row.hasPointerCapture(event.pointerId)) {
      row.releasePointerCapture(event.pointerId);
    }
    dragState.current.pointerId = -1;
    setDraggingSuggestions(false);
  };

  return (
    <div className="composer-wrap">
      <div
        ref={suggestionsRef}
        className={`suggestions-row${draggingSuggestions ? " is-dragging" : ""}`}
        onWheel={handleSuggestionsWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={stopDragging}
        onPointerCancel={stopDragging}
      >
        {SUGGESTIONS.map((s) => (
          <Button
            key={s.title}
            size="small"
            className="suggestion-chip"
            disabled={disabled}
            onClick={() => {
              if (!dragState.current.moved) onSend(s.prompt);
              dragState.current.moved = false;
            }}
          >
            {s.title}
          </Button>
        ))}
      </div>
      <div className="composer">
        <TextArea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Message FTSM-RAG Assistant..."
          autoSize={{ minRows: 1, maxRows: 6 }}
          maxLength={1500}
          disabled={disabled}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          disabled={disabled || !text.trim()}
        />
      </div>
      <p className="disclaimer">
        This assistant can make mistakes. Verify critical deadlines through official UKM channels.
      </p>
    </div>
  );
}
