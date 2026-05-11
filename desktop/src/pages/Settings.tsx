import { useEffect, useState, useMemo } from "react";
import { Input, Button, Select, Typography, Card, Space, message, Tag, Radio } from "antd";
import { ArrowLeftOutlined, EyeOutlined, EyeInvisibleOutlined, ReloadOutlined } from "@ant-design/icons";
import { Link, useNavigate } from "react-router-dom";
import { useSettings } from "../hooks/useSettings";

const { Text } = Typography;

const BUILTIN_MODELS: string[] = ["qwen-turbo"];

export default function Settings() {
  const { settings: saved, models, saving, load, loadModels, save } = useSettings();
  const navigate = useNavigate();

  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [region, setRegion] = useState<"china" | "intl">("china");
  const [baseUrl, setBaseUrl] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [customModel, setCustomModel] = useState("");
  const [useCustomModel, setUseCustomModel] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [keyStatus, setKeyStatus] = useState<{ valid?: boolean | null; error?: string }>({});
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (saved && !initialized) {
      setApiKey(saved.dashscope_api_key || "");
      const isIntl = (saved.dashscope_base_url || "").includes("dashscope-intl");
      setRegion(isIntl ? "intl" : "china");
      setBaseUrl(isIntl ? saved.dashscope_base_url : "");
      const savedModel = saved.chat_model_name || "";
      if (savedModel && !BUILTIN_MODELS.includes(savedModel)) {
        setUseCustomModel(true);
        setCustomModel(savedModel);
        setSelectedModel("__custom__");
      } else {
        setSelectedModel(savedModel);
      }
      setInitialized(true);
    }
  }, [saved, initialized]);

  // Merge builtin + API models, deduplicate
  const modelOptions = useMemo(() => {
    const apiModels = models?.models || [];
    const merged = [...new Set([...BUILTIN_MODELS, ...apiModels])];
    return [
      ...merged.map((m) => ({ value: m, label: m })),
      { value: "__custom__", label: "✏️ Custom model..." },
    ];
  }, [models]);

  // Filter options based on search text, and add custom typed value
  const filteredOptions = useMemo(() => {
    if (!searchText) return modelOptions;
    const filtered = modelOptions.filter((opt) =>
      opt.label.toLowerCase().includes(searchText.toLowerCase())
    );
    // If typed text doesn't match any existing option exactly, offer to add it
    const exactMatch = modelOptions.some(
      (opt) => opt.value.toLowerCase() === searchText.toLowerCase()
    );
    if (!exactMatch && searchText.trim()) {
      filtered.push({ value: searchText.trim(), label: `✏️ Use "${searchText.trim()}"` });
    }
    return filtered;
  }, [searchText, modelOptions]);

  const handleVerify = async () => {
    const data = await loadModels(region);
    if (data) {
      setKeyStatus({ valid: data.key_valid, error: data.key_error });
      if (data.key_valid) {
        message.success(`API Key valid — ${data.models.length} models synced.`);
      }
    }
  };

  const handleModelChange = (val: string) => {
    if (val === "__custom__") {
      setUseCustomModel(true);
      setSelectedModel("__custom__");
      setSearchText("");
    } else {
      setUseCustomModel(false);
      setSelectedModel(val);
      setSearchText("");
    }
  };

  const handleSave = async () => {
    const isMasked = apiKey.startsWith("sk-****") && apiKey.length <= 12;
    const keyToSend = isMasked ? "" : apiKey.trim();
    if (!keyToSend && !isMasked) {
      message.error("API key cannot be empty.");
      return;
    }

    const modelToSave = useCustomModel ? customModel.trim() : selectedModel;
    if (!modelToSave) {
      message.error("Please select or enter a model.");
      return;
    }

    const success = await save({
      dashscope_api_key: keyToSend,
      dashscope_base_url: baseUrl,
      chat_model_name: modelToSave,
    });

    if (success) {
      message.success("Settings saved. Redirecting...");
      setTimeout(() => navigate("/"), 900);
    } else {
      message.error("Failed to save settings.");
    }
  };

  return (
    <div className="settings-shell">
      <div className="settings-header">
        <Text type="secondary" style={{ letterSpacing: 1, fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>
          FTSM-RAG
        </Text>
        <h1>Settings</h1>
        <p>Configure your DashScope API credentials and model.</p>
        <Link to="/" className="settings-back">
          <ArrowLeftOutlined /> Back to Chat
        </Link>
      </div>

      <Card className="settings-card">
        <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Text strong>DashScope API Key</Text>
              <Tag color="red">Required</Tag>
            </div>
            <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 8 }}>
              Used for the chat model, embeddings, and image text extraction.
            </Text>
            <Input
              type={showKey ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-xxxxxxxxxxxxxxxx"
              suffix={
                <Button
                  type="text"
                  size="small"
                  icon={showKey ? <EyeInvisibleOutlined /> : <EyeOutlined />}
                  onClick={() => setShowKey(!showKey)}
                />
              }
            />
          </div>

          <div>
            <Text strong style={{ display: "block", marginBottom: 8 }}>Service Region</Text>
            <Radio.Group
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              buttonStyle="solid"
            >
              <Radio.Button value="china">China (dashscope.aliyuncs.com)</Radio.Button>
              <Radio.Button value="intl">International (dashscope-intl.aliyuncs.com)</Radio.Button>
            </Radio.Group>
          </div>

          <div>
            <Text strong style={{ display: "block", marginBottom: 8 }}>Chat Model</Text>
            <Space style={{ width: "100%" }}>
              {useCustomModel ? (
                <Input
                  value={customModel}
                  onChange={(e) => setCustomModel(e.target.value)}
                  placeholder="Enter model name, e.g. qwen-plus"
                  style={{ minWidth: 280 }}
                  onBlur={() => {
                    if (!customModel.trim()) {
                      setUseCustomModel(false);
                      setSelectedModel("");
                    }
                  }}
                />
              ) : (
                <Select
                  showSearch
                  value={selectedModel || undefined}
                  onChange={handleModelChange}
                  onSearch={setSearchText}
                  onBlur={() => setSearchText("")}
                  placeholder="Select or type a model"
                  style={{ minWidth: 280 }}
                  options={filteredOptions}
                  filterOption={false}
                  notFoundContent={searchText ? `Type Enter to use "${searchText}"` : "No models found"}
                />
              )}
              <Button icon={<ReloadOutlined />} onClick={handleVerify}>
                Verify Key
              </Button>
            </Space>
            {useCustomModel && (
              <Button
                type="link"
                size="small"
                onClick={() => { setUseCustomModel(false); setCustomModel(""); }}
                style={{ padding: 0, marginTop: 4 }}
              >
                ← Back to preset models
              </Button>
            )}
            {keyStatus.valid === true && (
              <Text type="success" style={{ display: "block", marginTop: 4, fontSize: 12 }}>
                API Key valid — models synced.
              </Text>
            )}
            {keyStatus.valid === false && (
              <Text type="danger" style={{ display: "block", marginTop: 4, fontSize: 12 }}>
                {keyStatus.error || "Invalid API Key."}
              </Text>
            )}
            <Text type="secondary" style={{ display: "block", marginTop: 4, fontSize: 11 }}>
              {BUILTIN_MODELS.length} preset models available. You can also type a custom model name.
            </Text>
          </div>

          <Button type="primary" onClick={handleSave} loading={saving} block>
            Save & apply
          </Button>
        </Space>
      </Card>
    </div>
  );
}
