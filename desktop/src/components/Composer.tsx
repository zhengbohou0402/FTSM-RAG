import { useState } from "react";
import { Button, Input } from "antd";
import { SendOutlined } from "@ant-design/icons";

const { TextArea } = Input;

interface Props {
  onSend: (text: string) => void;
  disabled: boolean;
}

const SUGGESTIONS = [
  { title: "Academic Calendar", prompt: "Where can I view the academic calendar?" },
  { title: "Course Timetable", prompt: "How do I check my course timetable?" },
  { title: "Admission Info", prompt: "What are the admission requirements for FTSM postgraduate programs?" },
  { title: "Visa Renewal", prompt: "How do I renew my student visa?" },
  { title: "Campus Bus", prompt: "How can I check UKM campus bus routes?" },
  { title: "Staff Directory", prompt: "How can I find FTSM academic staff and their expertise?" },
  { title: "Registration", prompt: "What should I prepare for course registration renewal?" },
  { title: "Industrial Training", prompt: "Where can I find industrial training information and contacts?" },
  { title: "Facilities", prompt: "What facilities and services are available at FTSM?" },
  { title: "Public Holidays", prompt: "What are the Malaysian public holidays for this academic year?" },
  { title: "Student Systems", prompt: "Which UKM student systems should I use for academic matters?" },
  { title: "Exam Schedule", prompt: "Where can I check my final exam schedule?" },
];

export default function Composer({ onSend, disabled }: Props) {
  const [text, setText] = useState("");

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };

  return (
    <div className="composer-wrap">
      <div className="suggestions-row">
        {SUGGESTIONS.map((s) => (
          <Button
            key={s.title}
            size="small"
            className="suggestion-chip"
            disabled={disabled}
            onClick={() => onSend(s.prompt)}
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
