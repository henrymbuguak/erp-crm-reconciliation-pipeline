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
        bindFunctions?.(container);
      } catch (error) {
        container.replaceWith(element);
        console.error("Unable to render Mermaid diagram", error);
      }
    }),
  );
});
