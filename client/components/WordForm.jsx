import { useEffect, useState } from "react";

import { api } from "../lib/api.js";
import Sheet from "./Sheet.jsx";

const EMPTY = { term: "", meaning: "", pos: "", alt: "", phonetic: "", example: "", tags: "" };

const FIELDS = [
  { key: "term", label: "单词", placeholder: "例如 pharmaceutical", required: true },
  { key: "meaning", label: "中文释义", placeholder: "例如 制药的；药物", required: true },
  { key: "pos", label: "词性（可选）", placeholder: "例如 n., adj." },
  { key: "alt", label: "可接受的其它英文答案（逗号分隔）", placeholder: "例如 colour, colourway" },
  { key: "phonetic", label: "音标（可选）", placeholder: "例如 /ˌfɑːməˈsuːtɪkl/" },
  { key: "tags", label: "标签（逗号分隔，可选）", placeholder: "例如 class-note, medicine" },
  { key: "example", label: "例句（可选）", placeholder: "", multiline: true },
];

export default function WordForm({ open, word, onClose, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setForm(word ? { ...EMPTY, ...pickWord(word) } : EMPTY);
    setError("");
  }, [open, word]);

  function update(key, value) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    if (!form.term.trim() || !form.meaning.trim()) {
      setError("单词和释义不能为空");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const payload = Object.fromEntries(Object.entries(form).map(([key, value]) => [key, value.trim()]));
      const saved = word ? await api.updateWord(word.id, payload) : await api.createWord(payload);
      onSaved?.(saved);
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet open={open} title={word ? "编辑单词" : "新增单词"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        {FIELDS.map((field) => (
          <label key={field.key} className="block">
            <span className="mb-1 block text-sm text-slate-600 dark:text-slate-300">
              {field.label}
              {field.required ? <span className="ml-0.5 text-rose-500">*</span> : null}
            </span>
            {field.multiline ? (
              <textarea
                value={form[field.key]}
                onChange={(event) => update(field.key, event.target.value)}
                rows={2}
                placeholder={field.placeholder}
                className="input resize-y"
              />
            ) : (
              <input
                value={form[field.key]}
                onChange={(event) => update(field.key, event.target.value)}
                placeholder={field.placeholder}
                autoCapitalize={field.key === "term" ? "none" : undefined}
                autoCorrect="off"
                spellCheck={false}
                className="input"
              />
            )}
          </label>
        ))}
        {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose} className="btn-ghost flex-1">
            取消
          </button>
          <button type="submit" disabled={saving} className="btn-primary flex-1">
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </form>
    </Sheet>
  );
}

function pickWord(word) {
  return {
    term: word.term || "",
    meaning: word.meaning || "",
    pos: word.pos || "",
    alt: word.alt || "",
    phonetic: word.phonetic || "",
    example: word.example || "",
    tags: word.tags || "",
  };
}
