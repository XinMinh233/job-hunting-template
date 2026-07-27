(() => {
  "use strict";

  const SPECIAL_INLINE = new Set(["\\", "`", "*", "_", "~", "[", "<", "\n"]);

  function safeLink(raw) {
    const value = raw.trim();
    if (value.startsWith("#") || value.startsWith("/")) return value;
    try {
      const parsed = new URL(value);
      if (["http:", "https:", "mailto:"].includes(parsed.protocol)) return value;
    } catch {
      return null;
    }
    return null;
  }

  function appendLink(parent, label, href) {
    const safeHref = safeLink(href);
    if (!safeHref) {
      parent.append(document.createTextNode(`[${label}](${href})`));
      return;
    }
    const link = document.createElement("a");
    link.href = safeHref;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    appendInline(link, label, 1);
    parent.append(link);
  }

  function appendInline(parent, source, depth = 0) {
    if (!source || depth > 12) {
      parent.append(document.createTextNode(source || ""));
      return;
    }

    let index = 0;
    while (index < source.length) {
      if (source[index] === "\\" && index + 1 < source.length) {
        parent.append(document.createTextNode(source[index + 1]));
        index += 2;
        continue;
      }

      if (source[index] === "\n") {
        parent.append(document.createElement("br"));
        index += 1;
        continue;
      }

      if (source[index] === "`") {
        const marker = source[index + 1] === "`" ? "``" : "`";
        const end = source.indexOf(marker, index + marker.length);
        if (end !== -1) {
          const code = document.createElement("code");
          code.textContent = source.slice(index + marker.length, end);
          parent.append(code);
          index = end + marker.length;
          continue;
        }
      }

      const pair = source.slice(index, index + 2);
      if (pair === "**" || pair === "__" || pair === "~~") {
        const end = source.indexOf(pair, index + 2);
        if (end !== -1) {
          const node = document.createElement(pair === "~~" ? "del" : "strong");
          appendInline(node, source.slice(index + 2, end), depth + 1);
          parent.append(node);
          index = end + 2;
          continue;
        }
      }

      if (source[index] === "[") {
        const match = source.slice(index).match(/^\[([^\]\n]+)\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/);
        if (match) {
          appendLink(parent, match[1], match[2]);
          index += match[0].length;
          continue;
        }
      }

      if (source[index] === "<") {
        const match = source.slice(index).match(/^<(https?:\/\/[^ >]+|mailto:[^ >]+)>/);
        if (match) {
          appendLink(parent, match[1], match[1]);
          index += match[0].length;
          continue;
        }
      }

      if (source[index] === "*" || source[index] === "_") {
        const marker = source[index];
        const end = source.indexOf(marker, index + 1);
        if (end > index + 1) {
          const emphasis = document.createElement("em");
          appendInline(emphasis, source.slice(index + 1, end), depth + 1);
          parent.append(emphasis);
          index = end + 1;
          continue;
        }
      }

      let next = index + 1;
      while (next < source.length && !SPECIAL_INLINE.has(source[next])) next += 1;
      parent.append(document.createTextNode(source.slice(index, next)));
      index = next;
    }
  }

  function splitTableRow(line) {
    let value = line.trim();
    if (value.startsWith("|")) value = value.slice(1);
    if (value.endsWith("|") && !value.endsWith("\\|")) value = value.slice(0, -1);
    const cells = [];
    let cell = "";
    let escaped = false;
    for (const character of value) {
      if (escaped) {
        cell += character;
        escaped = false;
      } else if (character === "\\") {
        escaped = true;
      } else if (character === "|") {
        cells.push(cell.trim());
        cell = "";
      } else {
        cell += character;
      }
    }
    cells.push(cell.trim());
    return cells;
  }

  function tableDelimiter(line) {
    const cells = splitTableRow(line);
    return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
  }

  function startsBlock(lines, index) {
    const line = lines[index] || "";
    const next = lines[index + 1] || "";
    return (
      /^\s*$/.test(line)
      || /^ {0,3}(#{1,6})\s+/.test(line)
      || /^ {0,3}(`{3,}|~{3,})/.test(line)
      || /^ {0,3}>\s?/.test(line)
      || /^ {0,3}([-+*]|\d+[.)])\s+/.test(line)
      || /^ {0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$/.test(line)
      || (line.includes("|") && tableDelimiter(next))
    );
  }

  function renderTable(container, lines, start) {
    const headings = splitTableRow(lines[start]);
    const alignments = splitTableRow(lines[start + 1]).map((cell) => {
      const left = cell.startsWith(":");
      const right = cell.endsWith(":");
      return left && right ? "center" : right ? "right" : left ? "left" : "";
    });
    const table = document.createElement("table");
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    headings.forEach((heading, column) => {
      const cell = document.createElement("th");
      if (alignments[column]) cell.style.textAlign = alignments[column];
      appendInline(cell, heading);
      headRow.append(cell);
    });
    head.append(headRow);
    table.append(head);

    const body = document.createElement("tbody");
    let index = start + 2;
    while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
      const row = document.createElement("tr");
      const values = splitTableRow(lines[index]);
      headings.forEach((_heading, column) => {
        const cell = document.createElement("td");
        if (alignments[column]) cell.style.textAlign = alignments[column];
        appendInline(cell, values[column] || "");
        row.append(cell);
      });
      body.append(row);
      index += 1;
    }
    table.append(body);
    const wrapper = document.createElement("div");
    wrapper.className = "markdown-table-wrap";
    wrapper.append(table);
    container.append(wrapper);
    return index;
  }

  function renderInto(container, markdown) {
    const lines = String(markdown || "").replace(/\r\n?/g, "\n").split("\n");
    let index = 0;

    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) {
        index += 1;
        continue;
      }

      const fence = line.match(/^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)?.*$/);
      if (fence) {
        const marker = fence[1];
        const codeLines = [];
        index += 1;
        while (index < lines.length && !new RegExp(`^ {0,3}${marker[0]}{${marker.length},}\\s*$`).test(lines[index])) {
          codeLines.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) index += 1;
        const pre = document.createElement("pre");
        const code = document.createElement("code");
        if (fence[2]) code.className = `language-${fence[2].replace(/[^a-zA-Z0-9_-]/g, "")}`;
        code.textContent = codeLines.join("\n");
        pre.append(code);
        container.append(pre);
        continue;
      }

      const heading = line.match(/^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);
      if (heading) {
        const node = document.createElement(`h${heading[1].length}`);
        appendInline(node, heading[2]);
        container.append(node);
        index += 1;
        continue;
      }

      if (/^ {0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$/.test(line)) {
        container.append(document.createElement("hr"));
        index += 1;
        continue;
      }

      if (line.includes("|") && index + 1 < lines.length && tableDelimiter(lines[index + 1])) {
        index = renderTable(container, lines, index);
        continue;
      }

      if (/^ {0,3}>\s?/.test(line)) {
        const quoted = [];
        while (index < lines.length && /^ {0,3}>\s?/.test(lines[index])) {
          quoted.push(lines[index].replace(/^ {0,3}>\s?/, ""));
          index += 1;
        }
        const blockquote = document.createElement("blockquote");
        renderInto(blockquote, quoted.join("\n"));
        container.append(blockquote);
        continue;
      }

      const listItem = line.match(/^ {0,3}([-+*]|\d+[.)])\s+(.+)$/);
      if (listItem) {
        const ordered = /^\d/.test(listItem[1]);
        const list = document.createElement(ordered ? "ol" : "ul");
        while (index < lines.length) {
          const item = lines[index].match(/^ {0,3}([-+*]|\d+[.)])\s+(.+)$/);
          if (!item || /^\d/.test(item[1]) !== ordered) break;
          const node = document.createElement("li");
          appendInline(node, item[2]);
          list.append(node);
          index += 1;
        }
        container.append(list);
        continue;
      }

      const paragraphLines = [line];
      index += 1;
      while (index < lines.length && !startsBlock(lines, index)) {
        paragraphLines.push(lines[index]);
        index += 1;
      }
      const paragraph = document.createElement("p");
      appendInline(paragraph, paragraphLines.join("\n"));
      container.append(paragraph);
    }
  }

  function render(container, markdown) {
    const fragment = document.createDocumentFragment();
    renderInto(fragment, markdown);
    container.replaceChildren(fragment);
    container.classList.add("markdown-body");
  }

  window.JobHuntMarkdown = {render};
})();
