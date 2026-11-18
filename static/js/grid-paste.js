/* Paste a block of cells from Excel into the marks grid, and move between rows with the arrow
   keys. The grid is an ordinary form: this only fills the boxes, nothing is saved until the
   person presses Save. Without JavaScript the grid still works box by box. */
(function () {
  "use strict";

  function cellInputs(table) {
    return Array.prototype.map.call(table.rows, function (row) {
      return Array.prototype.filter.call(row.querySelectorAll("input"), function (input) {
        return input.name.indexOf("cell:") === 0;
      });
    }).filter(function (inputs) { return inputs.length > 0; });
  }

  function position(grid, input) {
    for (var r = 0; r < grid.length; r++) {
      var c = grid[r].indexOf(input);
      if (c !== -1) { return { row: r, col: c }; }
    }
    return null;
  }

  function notice(table, text) {
    var box = document.getElementById("paste-notice");
    if (!box) {
      box = document.createElement("p");
      box.id = "paste-notice";
      box.setAttribute("role", "status");
      table.parentNode.insertBefore(box, table);
    }
    box.textContent = text;
  }

  document.addEventListener("paste", function (event) {
    var target = event.target;
    if (!target || !target.name || target.name.indexOf("cell:") !== 0) { return; }
    var table = target.closest("table");
    var text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
    if (!table || text.indexOf("\t") === -1 && text.indexOf("\n") === -1) { return; }
    var grid = cellInputs(table);
    var start = position(grid, target);
    if (!start) { return; }
    event.preventDefault();
    var lines = text.replace(/\r\n?/g, "\n").replace(/\n+$/, "").split("\n");
    var filled = 0, skipped = 0;
    lines.forEach(function (line, i) {
      line.split("\t").forEach(function (value, j) {
        var row = grid[start.row + i];
        var input = row ? row[start.col + j] : undefined;
        if (!input) { skipped++; return; }
        input.value = value.trim();
        input.dispatchEvent(new Event("input", { bubbles: true }));
        filled++;
      });
    });
    notice(table, "Pasted " + filled + " cells" +
      (skipped ? " (" + skipped + " did not fit the grid and were left out)" : "") +
      ". Press Save to keep them.");
  });

  document.addEventListener("keydown", function (event) {
    var key = event.key;
    if (key !== "ArrowUp" && key !== "ArrowDown") { return; }
    var target = event.target;
    if (!target || !target.name || target.name.indexOf("cell:") !== 0) { return; }
    var grid = cellInputs(target.closest("table"));
    var at = position(grid, target);
    if (!at) { return; }
    var next = grid[at.row + (key === "ArrowDown" ? 1 : -1)];
    if (next && next[at.col]) {
      event.preventDefault();
      next[at.col].focus();
      next[at.col].select();
    }
  });
})();
