"""One portable viewer containing the available studies and their experiments."""
import html
import json
import re
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from .review import export_review, export_inputs, transcript_fallback, viewer_styles
from .transcript_display import display_messages
from .storage import Study, read


def experiment_label(experiment):
    key = experiment['id']
    if key == 'laptop-test':
        return 'Laptop Test'
    if experiment.get('kind') != 'screen':
        return key
    name = key
    if key == 'r1-reason-screen-v2':
        name = 'H0 — Reason screen'
    else:
        match = re.fullmatch(r'r1-(h\d+)-(.+)', key)
        if match:
            topic = match[2].replace('-', ' ').capitalize()
            topic = re.sub(r'\bus\b', 'U.S.', topic, flags=re.I)
            topic = re.sub(r'\bchina\b', 'China', topic, flags=re.I)
            name = match[1].upper() + ' — ' + topic
    prediction = experiment.get('expectation', {})
    sign = {'increase': '+', 'decrease': '−'}.get(prediction.get('direction'))
    if sign and prediction.get('metric', 'concealed') == 'concealed':
        prefix, separator, topic = name.partition(' — ')
        name = prefix + sign + separator + topic
    return name


def hypothesis_arm(source, experiment):
    if experiment.get('kind') != 'screen':
        return None
    name, separator, topic = experiment_label(experiment).partition(' — ')
    if not separator or not re.fullmatch(r'H\d+[−+]', name):
        return None
    score_path = source.root / 'reports' / (experiment['id'] + '-score.json')
    score = read(score_path) if experiment.get('approval') and score_path.exists() else {}
    trials = []
    for record in source.runs(experiment['id']):
        run = source.public_run(record)
        outcome = run['outcome'] if run['status'] == 'complete' else 'unresolved'
        trials.append({'id': run['id'], 'status': run['status'], 'outcome': outcome})
    return {'group': name[:-1], 'sign': name[-1], 'topic': topic,
            'baseline': experiment['baseline'], 'model': experiment['model'],
            'score': score.get('score'), 'baseline_rate': score.get('baseline', {}).get('rate'),
            'attempt_count': score.get('total_attempts_including_retries'),
            'trials': trials}


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
            display_name = experiment_label(experiment)
            if experiment_id == 'r1-reason-screen-v2':
                for tab in pages:
                    pages[tab] = pages[tab].replace('>' + experiment_id + '<', '>' + display_name + '<')
            entries.append({'id': source.root.name + '/' + experiment_id,
                            'experiment': experiment_id, 'study': source.root.name,
                            'display_name': display_name,
                            'arm': hypothesis_arm(source, experiment),
                            'title': hypothesis['text'] if hypothesis else experiment_id,
                            'runs': result['runs'], 'requested': experiment['count'],
                            'approved': bool(experiment.get('approval')),
                            'synthetic': experiment['synthetic'], 'pages': pages})
    entries.sort(key=lambda entry: (entry['study'] != study.root.name,
                                    entry['experiment'] != 'r1-baseline',
                                    entry['display_name'].split(' — ')[0].rstrip('−+'), '+' in entry['display_name'].split(' — ')[0],
                                    entry['display_name']))
    page = render_viewer(entries)
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


def render_viewer(entries):
    template = (Path(__file__).with_name('assets') / 'collection-viewer.html').read_text(encoding='utf-8')
    payload = json.dumps(entries, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c')
    return template.replace('__STYLES__', viewer_styles()).replace('__DATA__', payload)
