"""One portable viewer containing the available studies and their experiments."""
import html
import json
import re
from zipfile import ZipFile, ZIP_DEFLATED

from .review import export_review, export_inputs, transcript_fallback, viewer_styles
from .transcript_display import display_messages
from .storage import Study


def export_collection(study):
    studies = [study]
    for config in sorted(study.root.parent.glob('*/study.json')):
        if config.parent.resolve() != study.root:
            studies.append(Study(config.parent))
    entries = []
    for source in studies:
        for experiment in source.all('experiments'):
            if (experiment.get('synthetic', False)
                    or experiment.get('model') == 'v4-pro'
                    or experiment['id'] == 'r1-reason-screen'
                    or experiment['id'].startswith('r1-setup-check')):
                continue
            experiment_id = experiment['id']
            reports = source.root / 'reports'
            summary_path = reports / (experiment_id + '-review.html')
            previous = summary_path.read_text(encoding='utf-8') if summary_path.exists() else ''
            if 'kind' in experiment:
                result = export_review(source, experiment_id)
                summary = summary_path.read_text(encoding='utf-8')
            else:
                # Older setup checks predate the planned-experiment schema.
                runs = source.runs(experiment_id)
                result = {'runs': len(runs)}
                summary = '<h1>Archived setup check</h1><p>' + html.escape(experiment.get('purpose', experiment_id)) + '</p><p>' + str(len(runs)) + ' recorded slots</p>'
                export_inputs(source, experiment)
                records = [dict(id=run['id'], outcome=run['outcome'], display_messages=display_messages(run)) for run in runs]
                transcript = transcript_fallback(records).replace('<noscript>', '').replace('</noscript>', '')
                transcript = transcript.replace('Enable JavaScript to filter runs and save annotations. Public transcripts follow.', 'Archived setup-check messages')
                (reports / (experiment_id + '-transcripts.html')).write_text('<html><head><meta charset="utf-8"><style>' + viewer_styles() + '</style></head><body>' + transcript + '</body></html>', encoding='utf-8')
            # Retain the baseline's separately prepared statistical analysis.
            statistics = re.search(r'<!-- baseline-statistics:start -->.*?<!-- baseline-statistics:end -->', previous, re.S)
            if statistics:
                summary = summary.replace('</main>', statistics[0] + '</main>')
                summary_path.write_text(summary, encoding='utf-8')
            pages = {'summary': summary}
            for tab, suffix in [('inputs', 'inputs'), ('transcripts', 'transcripts'),
                                ('statistics', 'statistics'), ('accounting', 'accounting')]:
                path = reports / (experiment_id + '-' + suffix + '.html')
                if path.exists():
                    pages[tab] = path.read_text(encoding='utf-8')
            hypothesis = source.get('hypotheses', experiment['hypothesis']) if experiment.get('hypothesis') else None
            display_name = 'H0 — Reason screen' if experiment_id == 'r1-reason-screen-v2' else experiment_id
            if experiment_id == 'r1-reason-screen-v2':
                for tab in pages:
                    pages[tab] = pages[tab].replace('>' + experiment_id + '<', '>' + display_name + '<')
            entries.append({'id': source.root.name + '/' + experiment_id,
                            'experiment': experiment_id, 'study': source.root.name,
                            'display_name': display_name,
                            'title': hypothesis['text'] if hypothesis else experiment_id,
                            'runs': result['runs'], 'requested': experiment['count'],
                            'approved': bool(experiment.get('approval')),
                            'synthetic': experiment['synthetic'], 'pages': pages})
    entries.sort(key=lambda entry: (entry['study'] != study.root.name,
                                    entry['experiment'] != 'r1-baseline',
                                    '-h' not in entry['experiment'] and entry['experiment'] != 'r1-reason-screen-v2',
                                    entry['display_name']))
    payload = json.dumps(entries, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c')
    page = TEMPLATE.replace('__STYLES__', viewer_styles()).replace('__DATA__', payload)
    output = study.root / 'reports' / 'viewer.html'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding='utf-8')
    archive_path = output.with_name('viewer-laptop.zip')
    with ZipFile(archive_path, 'w', ZIP_DEFLATED) as archive:
        archive.write(output, 'viewer.html')
        hypothesis_doc = study.root.parent.parent / 'hypotheses.md'
        if hypothesis_doc.exists():
            archive.write(hypothesis_doc, 'hypotheses.md')
        archive.writestr('START-HERE.txt', 'Extract the ZIP and open viewer.html in your browser.\nChoose an experiment, then Summary, Inputs, or Transcripts.\nThe HTML contains the exported pages and works offline.\nDownload annotations to transfer review drafts between computers.\n')
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
    return {'viewer': str(output), 'zip': str(archive_path), 'experiments': len(entries),
            'recorded_slots': sum(entry['runs'] for entry in entries)}


TEMPLATE = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Model forensics viewer</title><style>__STYLES__
body{height:100vh;display:flex;flex-direction:column}.viewer-head{padding:16px 24px;border-bottom:1px solid var(--rule)}
.viewer-head h1{font-size:22px;margin-bottom:12px}.viewer-head select{width:100%;max-width:100%}
#tabs{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}#tabs button[aria-current]{background:var(--selection)}
#status{font-size:14px;margin:8px 0 0}iframe{flex:1;width:100%;border:0;min-height:400px}
</style></head><body><header class="viewer-head"><h1>Model forensics</h1>
<label for="experiment">Experiment</label><select id="experiment"></select><p id="status"></p>
<nav id="tabs" aria-label="Experiment views"></nav></header><iframe id="page" title="Experiment view"></iframe>
<script type="application/json" id="data">__DATA__</script><script>
const experiments = JSON.parse(document.getElementById('data').textContent);
const selector = document.getElementById('experiment');
const frame = document.getElementById('page');
const labels = {summary:'Summary', inputs:'Inputs', transcripts:'Transcripts', statistics:'Statistics', accounting:'Run accounting'};
let selected = experiments[0];
let activeTab = 'summary';
for (const entry of experiments) {
    const option = document.createElement('option');
    option.value = entry.id;
    option.textContent = entry.study + ' / ' + entry.display_name + ' (' + entry.runs + '/' + entry.requested + ' runs)' + (entry.synthetic ? ' — synthetic' : '');
    selector.append(option);
}
function show(tab) {
    if (!selected) return;
    activeTab = selected.pages[tab] ? tab : 'summary';
    selector.value = selected.id;
    document.getElementById('status').textContent = selected.title + ' · ' + selected.runs + ' recorded / ' + selected.requested + ' planned' + (selected.approved ? ' · Approved' : ' · Draft awaiting review');
    const tabs = document.getElementById('tabs');
    tabs.replaceChildren();
    for (const key of Object.keys(selected.pages)) {
        const button = document.createElement('button');
        button.textContent = labels[key];
        if (key === activeTab) button.setAttribute('aria-current', 'page');
        button.onclick = () => show(key);
        tabs.append(button);
    }
    frame.srcdoc = selected.pages[activeTab].replace('</head>', '<style>nav.view-tabs,div.view-tabs{display:none}</style></head>');
    history.replaceState(null, '', '#' + encodeURIComponent(selected.id) + ':' + activeTab);
}
frame.onload = () => {
    frame.contentDocument.addEventListener('click', event => {
        const link = event.target.closest('a');
        if (!link) return;
        const href = link.getAttribute('href');
        const suffixes = {review:'summary', inputs:'inputs', transcripts:'transcripts', statistics:'statistics', accounting:'accounting'};
        for (const [suffix, tab] of Object.entries(suffixes)) {
            if (href === selected.experiment + '-' + suffix + '.html') {
                event.preventDefault();
                show(tab);
                return;
            }
        }
    });
};
selector.onchange = () => { selected = experiments.find(entry => entry.id === selector.value); show(activeTab); };
const saved = location.hash.slice(1).split(':');
if (saved[0]) selected = experiments.find(entry => entry.id === decodeURIComponent(saved[0])) || selected;
show(saved[1] || 'summary');
</script></body></html>'''
