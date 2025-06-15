"""
Python FlameGraph Generator
============================

This script generates an interactive flame graph SVG from stack trace data.
Similar to Brendan Gregg's flamegraph.pl, but implemented in pure Python.

Usage:
  python flamegraph.py [options] input_file > output.svg

Options:
  --title TEXT      Set title of flame graph
  --width NUM       Width of SVG image (default 1200)
  --height NUM      Height per sample (default 15)
  --minwidth NUM    Omit smaller functions (in pixels)
  --palette         Color palette (hot, mem, io, wakeup, chain, python)
  --countname TEXT  Count type label (samples, bytes, etc.)
  --reverse         Generate reverse flame graph
  --inverted        Generate icicle graph
  --flamechart      Generate flame chart (sort by time, not alphabetically)

Input format:
  Each line should contain a semicolon-separated stack trace followed by a space and a count:
    func_a;func_b;func_c 100
    func_a;func_d 50
"""  # noqa: E501

import argparse
import collections
import hashlib
import html
import os
import sys
from collections import defaultdict


class FlameGraph:
    class Node:
        __slots__ = ("children", "depth", "name", "parent", "total", "width", "x")

        def __init__(self, name: str):
            """
            Initialize a flame graph node with the given name.

            Args:
                name (str): The name of the node.

            Attributes:
                name (str): Node identifier.
                total (int): Total value associated with this node.
                children (dict): Child nodes organized by name.
                x (int): X-coordinate position for visualization.
                depth (int): Depth level in the flame graph hierarchy.
            """
            self.name = name
            self.total = 0
            self.children: dict[str, FlameGraph.Node] = {}
            self.x: float = 0
            self.depth = 0
            self.parent: None | FlameGraph.Node = None
            self.width: float = 0

        def __str__(self):
            return f"{self.name} ({self.total})"

        def __repr__(self):
            return f"{self.name} ({self.total})"

    def __init__(
        self,
        lines: list[str],
        reverse: bool = False,
        height: int = 15,
        width: int = 1200,
        minwidth: float = 0.1,
        title: str = "Flame Graph",
        countname: str = "samples",
        command: str = "",
        package_path: str = "",
        work_dir: str = "",
    ) -> None:
        """Initialize a FlameGraph instance with given parameters.

        Args:
            lines (list[str]): List of stack trace lines to process.
            reverse (bool): If True, reverse the stack order (default: False).
            height (int): Height of the flame graph in lines (default: 15).
            width (int): Width of the flame graph in characters (default: 1200).
            minwidth (float): Minimum width percentage for a frame to be shown (default: 0.1).
            title (str): Title of the flame graph (default: "Flame Graph").
            countname (str): Label for the count/samples (default: "samples").
            command (str): Command that generated the profile data.
            package_path (str): Path to the package being analyzed.
            work_dir (str): Working directory for the analysis.
            output_file (str): Path to save the output flame graph.
        """  # noqa: E501
        self.lines = lines
        self.reverse = reverse
        self.height = height
        self.width = width
        self.minwidth = minwidth
        self.countname = countname
        self.title = title
        self.command = command
        self.work_dir = work_dir
        self.package_path = package_path
        self.stacks: dict[str, int] = defaultdict(int)
        self.total_samples = 0
        self.max_depth = 0

    def parse_input(self) -> None:
        """Parse input file and aggregate stack counts"""
        for line in self.lines:
            line = line.strip()
            if not line:
                continue

            # Split count and stack
            parts: list[str] = line.rsplit(" ", 1)
            if len(parts) != 2:
                print(f"Invalid line(ignored): {line}", file=sys.stderr)
                continue

            stack, count_str = parts
            try:
                count = int(count_str)
            except ValueError:
                print(f"Invalid line(ignored): {line}", file=sys.stderr)
                continue

            frames = stack.split(";")

            if self.reverse:
                frames.reverse()

            self.stacks[";".join(frames)] += count
            self.total_samples += count
            self.max_depth = max(self.max_depth, len(frames))

    def build_call_tree(self):
        """Builds a call tree from collected stack traces.

        Processes each stack trace in self.stacks, splitting it into individual frames
        and constructing a hierarchical tree structure where each node represents a
        function call. The root node represents the entry point ('root'), and child
        nodes represent subsequent function calls. Each node's total attribute is
        incremented by the count of occurrences for that call path.

        Returns:
            Node: The root node of the constructed call tree with aggregated counts.
        """
        root = self.Node("root")

        for stack, count in self.stacks.items():
            frames = stack.split(";")
            node = root
            node.total += count

            for frame in frames:
                if frame not in node.children:
                    child = self.Node(frame)
                    node.children[frame] = child
                    child.parent = node

                node = node.children[frame]
                node.total += count

        return root

    def layout_tree(self, node: Node, x: float, scale: float) -> None:
        """Recursively lays out a tree node and its children horizontally.

        Args:
            node: The current node to layout.
            x: The starting x-coordinate for this node.
            scale: The scaling factor to apply to node widths.

        The method sets the node's position and width, sorts its children by name,
        updates their depths, and recursively lays out each child node.
        """
        node.x = x
        node.width = node.total * scale
        try:
            sorted_children = sorted(
                node.children.values(), key=lambda n: int(n.name.split(":")[-1])
            )
        except ValueError:
            sorted_children = list(node.children.values())

        for child in sorted_children:
            child.depth = node.depth + 1

        current_x = x
        for child in sorted_children:
            self.layout_tree(child, current_x, scale)
            current_x += child.width

    def collect_nodes_by_depth(self, root: Node) -> dict[int, list[Node]]:
        """Collect nodes grouped by their depth using BFS traversal.

        Args:
            root: The root node of the tree to traverse.

        Returns:
            defaultdict: A dictionary mapping depth levels to lists of nodes at that depth.
            Note: The root node (depth=0) is excluded from the results.
        """  # noqa: E501
        nodes_by_depth: dict[int, list[FlameGraph.Node]] = defaultdict(list)
        queue = collections.deque([root])

        while queue:
            node = queue.popleft()
            if node.depth > 0:
                nodes_by_depth[node.depth].append(node)

            try:
                sorted_children = sorted(
                    node.children.values(), key=lambda n: int(n.name.split(":")[-1])
                )
            except ValueError:
                sorted_children = list(node.children.values())
            for child in sorted_children:
                queue.append(child)

        return nodes_by_depth

    def get_stack_path(self, node):
        path = []
        while node and node.name != "root":
            path.append(node.name)
            node = getattr(node, "parent", None)

        return ";".join(reversed(path))

    def generate_svg(self) -> str:
        """Generate SVG flame graph with proper layout"""
        root = self.build_call_tree()

        scale = (self.width - 20) / root.total
        root.depth = 1
        self.layout_tree(root, 10, scale)

        nodes_by_depth = self.collect_nodes_by_depth(root)
        max_depth = max(nodes_by_depth.keys()) if nodes_by_depth else 0
        height = max_depth * self.height + 170

        # SVG header
        svg = [
            '<?xml version="1.0" standalone="no"?>',
            '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">',
            f'<svg version="1.1" width="{self.width}" height="{height}"',
            f'onload="init(evt)" viewBox="0 0 {self.width} {height}"',
            'xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">',
            "<!-- Flame graph stack visualization. See https://github.com/brendangregg/FlameGraph for latest version, and http://www.brendangregg.com/flamegraphs.html for examples. -->",  # noqa: E501
            "<!-- NOTES:  -->",
            "<defs>",
            '<linearGradient id="background" y1="0" y2="1" x1="0" x2="0">',
            '<stop stop-color="#eeeeee" offset="5%" />',
            '<stop stop-color="#eeeeb0" offset="95%" />',
            "</linearGradient>",
            "</defs>",
            '<style type="text/css">',
            "text { font-family: Source Serif Pro, Palatino, gentium plus, Arial, sans-serif; font-size: 11px; fill: rgb(0, 0, 0);}",  # noqa: E501
            "#search, #ignorecase { opacity: 0.1; cursor: pointer; }",
            "#search:hover, #search.show, #ignorecase:hover, #ignorecase.show { opacity: 1; }",  # noqa: E501
            "#subtitle { text-anchor: middle; font-color: rgb(160, 160, 160);}",
            "#title { text-anchor: middle; font-size: 17px }",
            "#under_title { text-anchor: middle; font-size: 13px }",
            "#unzoom { cursor: pointer; }",
            "#frames > *:hover { stroke: black; stroke-width: 0.5; cursor: pointer; }",
            ".hide { display: none; }",
            ".parent { opacity: 0.5; }",
            "</style>",
            '<script type="text/ecmascript">\n<![CDATA[',
            self.get_javascript(),
            "]]>\n</script>",
            f'<rect x="0" y="0" width="{self.width}" height="{height}" fill="url(#background)" rx="2" ry="2" />',  # noqa: E501
            f'<text id="title" x="{self.width // 2}" y="24">{self.title}</text>',
            f'<text id="under_title" x="{self.width // 2}" y="44">Environment: {self.package_path}</text>',  # noqa: E501
            f'<text id="under_title" x="{self.width // 2}" y="64">Working Directory: {self.work_dir}</text>',  # noqa: E501
            f'<text id="under_title" x="{self.width // 2}" y="84">Command: {self.command}</text>',  # noqa: E501
            f'<text id="details" x="10" y="{height - 10}"> </text>',
            '<text id="unzoom" x="10" y="24" class="hide">Reset Zoom</text>',
            f'<text id="search" x="{self.width - 110}" y="24">Search</text>',
            f'<text id="ignorecase" x="{self.width - 30}" y="24">ic</text>',
            f'<text id="matched" x="{self.width - 110}" y="{height - 10}"> </text>',
            '<g id="frames">',
        ]

        for depth in sorted(nodes_by_depth.keys()):
            for node in nodes_by_depth[depth]:
                y = 50 + depth * self.height
                width = node.width
                if width < self.minwidth:
                    continue

                color = self.get_color(node.name)
                text = self.trim_text(node.name, width)

                frame_svg = [
                    "<g>",
                    f"<title>{html.escape(node.name)} ({node.total} {self.countname}, {node.total / self.total_samples * 100:.2f}%)</title>",  # noqa: E501
                    f'<rect x="{node.x}" y="{height - y}" width="{width}" height="{self.height}" fill="{color}" rx="2" ry="2" />',  # noqa: E501
                    f'<text x="{node.x + 5}" y="{height - (y - self.height + 4.5)}">{html.escape(text)}</text>',  # noqa: E501
                    "</g>",
                ]
                svg.extend(frame_svg)

        svg.extend(["</g>", "</svg>"])
        return "\n".join(svg)

    def get_color(self, frame):
        """Generate color for frame based on its name"""
        # Hash function name to get consistent color
        hash_val = int(hashlib.md5(frame.encode()).hexdigest()[:8], 16)
        hue = hash_val % 360
        sat = 35 + (hash_val % 30)
        lum = 65 + (hash_val % 10)
        return f"hsl({hue}, {sat}%, {lum}%)"

    def trim_text(self, text: str, width: float) -> str:
        """Trim text to fit in the given width"""
        if width / 6.5 < 3:
            return ""
        if len(text) * 6.5 <= width:
            return text
        max_chars = int(width / 6.5) - 2
        return text[:max_chars] + ".."

    def get_javascript(self):
        """Return the JavaScript code for interactive features"""
        base = os.path.dirname(os.path.abspath(__file__))
        script = os.path.join(base, "script.js")
        with open(script) as f:
            content = f.read()
        return content


def process_stack_trace(lines: str, site_path: str, work_dir: str) -> list[str]:
    res: list[str] = []
    base_dir = "/".join(site_path.split("/")[:-1])
    for line in lines:
        line = line.strip()
        if not line:
            continue
        t = []
        for item in line.split(";"):
            item = item.removeprefix(site_path)
            item = item.removeprefix(work_dir)
            item = item.removeprefix(base_dir)
            if item[0] == "/":
                item = item[1:]
            t.append(item)
        res.append(";".join(t))
    return res


def main() -> None:
    import os
    import site

    parser = argparse.ArgumentParser(
        description="Generate flame graph SVG from stack traces"
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="Input file (default: stdin)",
    )
    parser.add_argument("--title", default="Flame Graph", help="Title text")
    parser.add_argument("--width", type=int, default=1200, help="SVG width")
    parser.add_argument("--height", type=int, default=15, help="Frame height")
    parser.add_argument("--minwidth", type=float, default=0.1, help="Minimum frame width")
    parser.add_argument("--countname", default="samples", help="Count type label")
    parser.add_argument(
        "--reverse", action="store_true", help="Generate reverse flame graph"
    )
    parser.add_argument("-o", "--output", help="Output file (default: result.svg)")

    args = parser.parse_args()

    flamegraph = FlameGraph(
        process_stack_trace(
            args.input.readlines(), site.getsitepackages()[0], os.getcwd()
        ),
        reverse=args.reverse,
        height=args.height,
        width=args.width,
        minwidth=args.minwidth,
        title=args.title,
        countname=args.countname,
        command=" ".join(["python", *sys.argv]),
        package_path="/".join(site.getsitepackages()[0].split("/")[:-1]),
        work_dir=os.getcwd(),
    )
    flamegraph.parse_input()
    svg = flamegraph.generate_svg()

    if args.output is None:
        print(
            "\033[91m"
            + "output file is not specified, using result.svg as default"
            + "\033[0m",
            file=sys.stderr,
        )
        args.output = "result.svg"
    with open(args.output, "w") as f:
        f.write(svg)


if __name__ == "__main__":
    main()
