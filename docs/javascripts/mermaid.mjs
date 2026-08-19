import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.12.1/dist/mermaid.esm.min.mjs";

mermaid.initialize({
  startOnLoad: false,
  securityLevel: "strict",
});

let diagramId = 0;

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

        bindFunctions?.(container);
      } catch (error) {
        container.replaceWith(element);
        console.error("Unable to render Mermaid diagram", error);
      }
    }),
  );
});
