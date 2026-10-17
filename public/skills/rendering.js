// Rendering skill: turns `render` messages from the phone into live content on
// the screen's surface. First skill of the phone↔screen channel.
//
// Message shape (sent by the phone over the WebSocket):
//   { skill: "render", kind: "text" | "markdown" | "image" | "clear", content?: string }
//
// Each render replaces the surface's previous content ("latest wins");
// `clear` empties and hides the surface again.

const KINDS = new Set(["text", "markdown", "image", "clear"]);

export const renderingSkill = {
  name: "rendering",

  canHandle(data) {
    return !!data && data.skill === "render" && KINDS.has(data.kind);
  },

  /**
   * @param {{kind: string, content?: string}} data
   * @param {{surface: HTMLElement, log: (msg: string) => void}} ctx
   */
  handle(data, { surface, log }) {
    ensureStyles();
    const content = typeof data.content === "string" ? data.content : "";

    switch (data.kind) {
      case "clear":
        surface.replaceChildren();
        surface.hidden = true;
        log("Rendering: screen cleared.");
        return;

      case "text": {
        const el = document.createElement("div");
        el.className = "render-text";
        el.textContent = content;
        show(surface, el);
        log("Rendering: text.");
        return;
      }

      case "markdown": {
        const el = document.createElement("div");
        el.className = "render-markdown";
        el.innerHTML = renderMarkdown(content);
        show(surface, el);
        log("Rendering: markdown.");
        return;
      }

      case "image": {
        if (!/^https?:\/\//i.test(content)) {
          log("Rendering: rejected image (only http(s) URLs are allowed).");
          return;
        }
        const el = document.createElement("img");
        el.className = "render-image";
        el.src = content;
        el.alt = "Image sent from phone";
        el.onerror = () => log("Rendering: image failed to load.");
        show(surface, el);
        log("Rendering: image.");
        return;
      }
    }
  },
};

function show(surface, el) {
  surface.replaceChildren(el);
  surface.hidden = false;
}

/**
 * Minimal, safe Markdown renderer. The source is HTML-escaped first, then a
 * small subset of Markdown is applied on top, so phone input can never inject
 * raw HTML into the screen.
 *
 * Supported: # ## ### headings, "- " lists, **bold**, *italic*, `code`,
 * [text](http… links), paragraphs.
 */
export function renderMarkdown(src) {
  const lines = escapeHtml(src).split(/\r?\n/);
  const out = [];
  let list = null; // open <ul> items, or null
  let paragraph = []; // pending plain lines

  const flushParagraph = () => {
    if (paragraph.length) {
      out.push(`<p>${paragraph.map(inline).join("<br>")}</p>`);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      out.push(`<ul>${list.join("")}</ul>`);
      list = null;
    }
  };

  for (const line of lines) {
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    const item = /^-\s+(.*)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
    } else if (item) {
      flushParagraph();
      (list ??= []).push(`<li>${inline(item[1])}</li>`);
    } else if (line.trim() === "") {
      flushParagraph();
      flushList();
    } else {
      flushList();
      paragraph.push(line);
    }
  }
  flushParagraph();
  flushList();
  return out.join("");
}

/** Inline Markdown on an already-escaped line: code, bold, italic, links. */
function inline(text) {
  return text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
    );
}

function escapeHtml(s) {
  return s.replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

/** Inject the skill's stylesheet once, so the skill is self-contained. */
function ensureStyles() {
  if (document.getElementById("rendering-skill-styles")) return;
  const style = document.createElement("style");
  style.id = "rendering-skill-styles";
  style.textContent = `
    .render-text {
      font-size: 2rem;
      font-weight: 600;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      text-align: center;
    }
    .render-markdown {
      text-align: left;
      font-size: 1.05rem;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }
    .render-markdown h1 { font-size: 1.6rem; margin: 0.4em 0 0.2em; }
    .render-markdown h2 { font-size: 1.3rem; margin: 0.4em 0 0.2em; }
    .render-markdown h3 { font-size: 1.1rem; margin: 0.4em 0 0.2em; }
    .render-markdown p { margin: 0.4em 0; }
    .render-markdown ul { margin: 0.4em 0; padding-left: 1.4em; }
    .render-markdown code {
      background: rgba(148, 163, 184, 0.2);
      border-radius: 4px;
      padding: 0.1em 0.35em;
      font-size: 0.95em;
    }
    .render-markdown a { color: #818cf8; }
    .render-image {
      max-width: 100%;
      max-height: 60vh;
      border-radius: 12px;
      display: block;
      margin: 0 auto;
    }
  `;
  document.head.append(style);
}
