"""
Standalone power visualization script.
Reads analysis JSON files and generates power curve images.
Usage: python power_visualization.py [analysis_json/*_analysis.json ...]
"""
import sys
import json
from pathlib import Path
from clintrial_agent.reporting import generate_power_plots


def main():
    json_dir = Path('analysis_json')
    if not json_dir.exists():
        print("No analysis_json/ directory found. Run the pipeline first.")
        return

    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        paths = list(json_dir.glob('*_analysis.json'))

    comparison_paths = list(json_dir.glob('*_comparison.json'))
    if comparison_paths:
        with open(comparison_paths[0]) as f:
            data = json.load(f)
            all_results = list(data.values())
            print(f"Loaded {len(all_results)} trials from {comparison_paths[0].name}")
            generate_power_plots(all_results)
            return

    all_results = []
    for p in paths:
        if '_analysis.json' in p.name and '_comparison.json' not in p.name:
            with open(p) as f:
                result = json.load(f)
                all_results.append(result)

    if not all_results:
        print("No analysis JSON files found.")
        return

    print(f"Loaded {len(all_results)} trial(s)")
    generate_power_plots(all_results)


if __name__ == '__main__':
    main()