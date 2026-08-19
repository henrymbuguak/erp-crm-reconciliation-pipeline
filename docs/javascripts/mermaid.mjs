import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.12.1/dist/mermaid.esm.min.mjs";

mermaid.initialize({
  startOnLoad: false,
  securityLevel: "strict",
});

let diagramId = 0;
let lightbox;

// Singleton overlay, reused by every diagram, created lazily on first click.
function getLightbox() {
  if (lightbox) return lightbox;

  const overlay = document.createElement("div");
  overlay.className = "mermaid-lightbox";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.innerHTML = `
    <button type="button" class="mermaid-lightbox__close" aria-label="Close">&times;</button>
    <div class="mermaid-lightbox__content"></div>
  `;
  document.body.append(overlay);

  const closeButton = overlay.querySelector(".mermaid-lightbox__close");
  let triggerElement;

  const close = () => {
    overlay.classList.remove("mermaid-lightbox--open");
    triggerElement?.focus();
  };
  const open = (triggeredBy) => {
    triggerElement = triggeredBy;
    overlay.classList.add("mermaid-lightbox--open");
    closeButton.focus();
  };

  overlay.addEventListener("click", (event) => {
    if (!event.target.closest("svg")) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && overlay.classList.contains("mermaid-lightbox--open")) close();
  });

  lightbox = { overlay, open };
  return lightbox;
}

function makeZoomable(container) {
  container.setAttribute("role", "button");
  container.setAttribute("tabindex", "0");
  container.setAttribute("aria-label", "View diagram full size");

  const openFromContainer = () => {
    const svg = container.querySelector("svg");
    if (!svg) return;

    const { overlay, open } = getLightbox();
    const content = overlay.querySelector(".mermaid-lightbox__content");
    content.replaceChildren(svg.cloneNode(true));
    open(container);
  };

  container.addEventListener("click", openFromContainer);
  container.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openFromContainer();
    }
  });
}

document$.subscribe(async () => {
  const diagrams = [...document.querySelectorAll(".mermaid-source")];

  await Promise.all(
    diagrams.map(async (element) => {
      const source = element.textContent.trim();
      const container = document.createElement("div");
      container.className = "mermaid";
      element.replaceWith(container);

      try {
        diagramId += 1;
        const { svg, bindFunctions } = await mermaid.render(
          `mermaid-diagram-${diagramId}`,
          source,
        );
        container.innerHTML = svg;

        // Mermaid sets width="100%" on the <svg>, which shrinks wide diagrams
        // down to the container width until the text is illegible. Pin the
        // width to the diagram's natural size instead, so .mermaid's
        // overflow-x: auto scrolls it rather than squashing it.
        const svgElement = container.querySelector("svg");
        const viewBox = svgElement?.getAttribute("viewBox")?.split(/\s+/).map(Number);
        if (viewBox?.[2]) {
          svgElement.removeAttribute("width");
          svgElement.style.width = `${viewBox[2]}px`;
        }

        makeZoomable(container);
        bindFunctions?.(container);
      } catch (error) {
        container.replaceWith(element);
        console.error("Unable to render Mermaid diagram", error);
      }
    }),
  );
});
