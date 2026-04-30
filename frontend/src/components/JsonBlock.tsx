import { useState } from 'react'

export function JsonBlock({ label, data }: { label: string; data: object | string }) {
  const [open, setOpen] = useState(false)
  const parsed = typeof data === 'string' ? (() => { try { return JSON.parse(data) } catch { return data } })() : data
  return (
    <div className="mt-1.5 text-[11px]">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-gray-400 hover:text-gray-600 font-mono transition-colors"
      >
        <span className={`transition-transform inline-block ${open ? 'rotate-90' : ''}`}>▶</span>
        {label}
      </button>
      {open && (
        <pre className="mt-1.5 bg-gray-950 text-green-400 rounded-xl px-4 py-3 overflow-x-auto text-[11px] leading-relaxed font-mono whitespace-pre-wrap border border-gray-800">
          {typeof parsed === 'string' ? parsed : JSON.stringify(parsed, null, 2)}
        </pre>
      )}
    </div>
  )
}
