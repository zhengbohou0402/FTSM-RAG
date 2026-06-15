import type { Message, Source } from "../api/client";

const THINK_RE = /__THINK__([\s\S]*?)__ENDTHINK__/g;
const SOURCE_HEADER_RE =
  /\n+\s*(?:Sources|Sumber|来源|参考来源|参考资料)\s*[:：]\s*\n?([\s\S]*)$/i;
const SOURCE_PREFIX_RE =
  /^(?:-\s*)?(?:\[(\d+)\]|(\d+)[.、，])\s*(.+)$/;
const TRUST_LABEL_RE = /\s+\[([^\]]+)\]/;
const CHUNK_RE = /^\s*[,，]\s*(?:chunk|第)\s*(\d+)\s*(?:块)?/i;
const EXCERPT_RE = /^\s*[:：]\s*(.*)$/;

function parseThinking(raw: string): { thinking: string[]; clean: string } {
  const thinking: string[] = [];
  const clean = raw.replace(THINK_RE, (_match, inner: string) => {
    const label = inner.trim();
    if (label) thinking.push(label);
    return "";
  });
  return { thinking, clean: clean.trim() };
}

function parseSourceLine(line: string): Source | null {
  const prefixed = line.match(SOURCE_PREFIX_RE);
  if (!prefixed) return null;

  let remainder = prefixed[3].trim();
  let file = remainder;
  let sourceType: string | undefined;
  let chunkIndex: number | undefined;
  let excerpt = "";

  const trustMatch = remainder.match(TRUST_LABEL_RE);
  if (trustMatch && trustMatch.index !== undefined) {
    file = remainder.slice(0, trustMatch.index).trim();
    sourceType = trustMatch[1].trim();
    remainder = remainder.slice(trustMatch.index + trustMatch[0].length);
  } else {
    const metadataStart = remainder.search(/\s*[,，]\s*(?:chunk|第)\s*\d+/i);
    const excerptStart = remainder.search(/\s*[:：]\s+/);
    const splitAt = [metadataStart, excerptStart]
      .filter((index) => index >= 0)
      .sort((a, b) => a - b)[0];
    if (splitAt !== undefined) {
      file = remainder.slice(0, splitAt).trim();
      remainder = remainder.slice(splitAt);
    } else {
      remainder = "";
    }
  }

  const chunkMatch = remainder.match(CHUNK_RE);
  if (chunkMatch) {
    chunkIndex = Number(chunkMatch[1]);
    remainder = remainder.slice(chunkMatch[0].length);
  }

  const excerptMatch = remainder.match(EXCERPT_RE);
  if (excerptMatch) excerpt = excerptMatch[1].trim();

  if (!file) return null;
  return {
    file,
    chunk_index: chunkIndex,
    excerpt,
    source_type: sourceType,
  };
}

function dedupeSources(sources: Source[]): Source[] {
  const unique = new Map<string, Source>();
  for (const source of sources) {
    const chunkKey = source.chunk_index === undefined ? "" : String(source.chunk_index);
    const key = `${source.file.toLowerCase()}|${chunkKey}`;
    const current = unique.get(key);
    if (!current) {
      unique.set(key, source);
      continue;
    }
    if (!current.excerpt && source.excerpt) current.excerpt = source.excerpt;
    if (!current.source_type && source.source_type) current.source_type = source.source_type;
  }
  return [...unique.values()];
}

function parseSources(raw: string): { content: string; sources?: Source[] } {
  const match = raw.match(SOURCE_HEADER_RE);
  if (!match || match.index === undefined) return { content: raw.trim() };

  const sources = dedupeSources(
    match[1]
      .split("\n")
      .map((line) => parseSourceLine(line.trim()))
      .filter((source): source is Source => source !== null),
  );

  if (!sources.length) return { content: raw.trim() };
  return {
    content: raw.slice(0, match.index).trim(),
    sources,
  };
}

export function parseAssistantMessage(raw: string, streaming = false): Message {
  const parsedThinking = parseThinking(raw);
  const parsedSources = parseSources(parsedThinking.clean);
  return {
    role: "assistant",
    content: parsedSources.content,
    thinking: parsedThinking.thinking.length ? parsedThinking.thinking : undefined,
    sources: parsedSources.sources,
    ...(streaming ? { streaming: true } : {}),
  };
}
