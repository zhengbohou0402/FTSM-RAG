import assert from "node:assert/strict";
import test from "node:test";

import { parseAssistantMessage } from "../src/utils/messageParser.ts";

test("parses and deduplicates legacy cached sources without excerpts", () => {
  const raw = `Here are the key academic calendar dates.

Sources:

[1] academic_calendar_2025_2026.txt [Official material]
[3] academic_calendar_2025_2026.txt [Official material]
[4] academic_calendar_2025_2026.txt [Official material]
[5] chinese_student_ftsm_pages_dev_browser_crawl.txt [Student guide]`;

  const message = parseAssistantMessage(raw);

  assert.equal(message.content, "Here are the key academic calendar dates.");
  assert.deepEqual(message.sources, [
    {
      file: "academic_calendar_2025_2026.txt",
      chunk_index: undefined,
      excerpt: "",
      source_type: "Official material",
    },
    {
      file: "chinese_student_ftsm_pages_dev_browser_crawl.txt",
      chunk_index: undefined,
      excerpt: "",
      source_type: "Student guide",
    },
  ]);
});

test("keeps separate chunks and excerpts from current source format", () => {
  const raw = `Answer body.

Sources:
- [1] calendar.txt [Official material], chunk 3: Semester one dates.
- [2] calendar.txt [Official material], chunk 7: Semester two dates.`;

  const message = parseAssistantMessage(raw);

  assert.equal(message.sources?.length, 2);
  assert.equal(message.sources?.[0].chunk_index, 3);
  assert.equal(message.sources?.[0].excerpt, "Semester one dates.");
  assert.equal(message.sources?.[1].chunk_index, 7);
});

test("supports Chinese source headings and numbered lines", () => {
  const raw = `回答正文。

参考来源：
1、calendar.txt [Official material]，第 2 块：校历摘要。`;

  const message = parseAssistantMessage(raw);

  assert.equal(message.content, "回答正文。");
  assert.equal(message.sources?.[0].file, "calendar.txt");
  assert.equal(message.sources?.[0].chunk_index, 2);
  assert.equal(message.sources?.[0].excerpt, "校历摘要。");
});
