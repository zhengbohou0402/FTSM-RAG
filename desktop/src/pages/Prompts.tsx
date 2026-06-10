import { useState, useEffect } from "react";
import { Button, Typography, Space, Input, message, Card } from "antd";
import { SaveOutlined } from "@ant-design/icons";

const { Text } = Typography;
const { TextArea } = Input;

export default function Prompts() {
  const [promptText, setPromptText] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    // Mock loading from localStorage
    const saved = localStorage.getItem("ftsm_system_prompt");
    if (saved) {
      setPromptText(saved);
    } else {
      setPromptText(
        "You are the FTSM GPT Assistant, designed to help students with UKM Fakulti Teknologi dan Sains Maklumat (FTSM) inquiries. Always be polite, concise, and refer to official academic calendars or guidelines when answering."
      );
    }
  }, []);

  const handleSave = () => {
    setSaving(true);
    setTimeout(() => {
      localStorage.setItem("ftsm_system_prompt", promptText);
      message.success("System prompt saved successfully (Mocked).");
      setSaving(false);
    }, 600);
  };

  return (
    <div className="admin-shell settings-shell">
      <div className="admin-header settings-header">
        <div>
          <Text type="secondary" className="page-kicker">FTSM GPT</Text>
          <h1>System Prompts</h1>
          <p>Configure the underlying persona and instructions for the FTSM assistant.</p>
        </div>
      </div>

      <div className="settings-layout">
        <section className="admin-panel settings-card">
          <Space orientation="vertical" size="large" className="settings-stack">
            <section>
              <div className="panel-title-row">
                <Text strong>Global System Prompt</Text>
              </div>
              <Text type="secondary" className="field-help">
                This prompt will be injected at the beginning of every conversation to steer the model's behavior.
              </Text>
              <TextArea
                rows={8}
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                placeholder="Enter system prompt here..."
                style={{ borderRadius: "12px", padding: "16px", fontSize: "14px" }}
              />
            </section>
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSave} loading={saving} block>
              Save Configuration
            </Button>
          </Space>
        </section>

        <aside className="admin-panel settings-side-panel">
          <Text strong>Suggestions</Text>
          <div className="info-grid settings-info-grid" style={{ marginTop: "16px" }}>
            <Card size="small" className="manage-card" style={{ cursor: "pointer", marginBottom: "8px" }} onClick={() => setPromptText("You are an official UKM FTSM academic advisor. Provide extremely formal and structured answers based on the retrieved documents. Do not hallucinate.")}>
              <Text strong style={{ fontSize: "12px" }}>Formal Advisor</Text>
              <p style={{ margin: 0, fontSize: "11px", color: "#888" }}>Strict and structured tone.</p>
            </Card>
            <Card size="small" className="manage-card" style={{ cursor: "pointer" }} onClick={() => setPromptText("You are a friendly senior student at UKM FTSM. Use a casual, welcoming tone to help freshmen navigate their new campus life, but keep the facts accurate.")}>
              <Text strong style={{ fontSize: "12px", color: "#2e6da4" }}>Friendly Senior</Text>
              <p style={{ margin: 0, fontSize: "11px", color: "#888" }}>Casual and welcoming tone.</p>
            </Card>
          </div>
        </aside>
      </div>
    </div>
  );
}
