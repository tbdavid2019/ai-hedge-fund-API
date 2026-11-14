"""Offline contract, synthesis, transport, and submission lifecycle regressions."""
import copy
import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from src.headline_contract import (ASSET_POLICIES, analyst_evidence, utc_now,
                                   validate_challenge, validate_context, validate_probabilities)
from src import headline_forecast as synthesis
from scripts import sync_headline_arena as cli


@pytest.fixture
def challenge():
    now = utc_now()
    return {'id': 'pilot-question', 'asset': 'ES', 'challenge_type': 'daily',
            'status': 'open', 'question': 'Will the frozen ES contract rise today?',
            'deadline': (now + timedelta(minutes=20)).isoformat(),
            'resolve_at': (now + timedelta(hours=6)).isoformat(),
            'contract_symbol': 'ESZ6', 'baseline_status': 'confirmed',
            'open_price_confirmed': True, 'open_price': 6000.0,
            'dead_zone_pct': 0.3, 'resolution_criteria': 'Compare frozen contract prices; exactly +/-0.3% is neutral.'}


@pytest.fixture
def context(challenge):
    return {'challenge_id': challenge['id'], 'prediction_ready': True,
            'contract_identity': {'symbol': 'ESZ6'},
            'baseline': {'price': 6000.0, 'status': 'confirmed'},
            'quote': {'price': 6010.0, 'contract_symbol': 'ESZ6', 'as_of': utc_now().isoformat(), 'is_delayed': False},
            'change_from_baseline_pct': 0.2}


@pytest.fixture
def analysis():
    signal = {'signal': 'bullish', 'confidence': 80, 'reasoning': 'Observed technical and news evidence. 市場證據。', 'data_coverage': {'news_count': 3, 'insider_count': 0}}
    rt = dict(signal, discussion_summary='Mixed evidence discussed. 已討論相異證據。',
              consensus_view='Slight upside. 略為看漲。', dissenting_opinions=['Downside risk. 下行風險。'])
    return {'decisions': {'SPY': {'action': 'hold', 'confidence': 90}},
            'analyst_signals': {key: {'SPY': copy.deepcopy(signal)} for key in ('technical_analyst_agent', 'sentiment_agent', 'warren_buffett_agent')},
            'round_table': {'SPY': rt}}


def test_persona_names_percentages_and_actual_round_table(analysis):
    assert cli.convert_hedge_decision_to_forecast(analysis, 'SPY', 'ES', 'warren_buffett')[:2] == ('bullish', 0.8)
    assert cli.convert_hedge_decision_to_forecast(analysis, 'SPY', 'ES', 'warren_buffett_agent')[:2] == ('bullish', 0.8)
    assert cli.convert_hedge_decision_to_forecast(analysis, 'SPY', 'ES')[:2] == ('bullish', 0.8)
    assert analyst_evidence(analysis, 'SPY', ['sentiment_analyst'])['sentiment_analyst']['confidence'] == 0.8
    with pytest.raises(ValueError):
        cli.convert_hedge_decision_to_forecast(analysis, 'SPY', 'ES', 'michael_burry')
    with pytest.raises(ValueError):
        cli.convert_hedge_decision_to_forecast({}, 'SPY', 'ES')


@pytest.mark.parametrize('value', [{}, {'bullish': .8, 'neutral': .1},
    {'bullish': 80, 'neutral': 10, 'bearish': 10}, {'bullish': float('nan'), 'neutral': 0, 'bearish': 0},
    {'bullish': float('inf'), 'neutral': 0, 'bearish': 0}, {'bullish': True, 'neutral': 0, 'bearish': 0},
    {'bullish': -.1, 'neutral': .5, 'bearish': .6}, {'bullish': .5, 'neutral': .5, 'bearish': .5}])
def test_invalid_probabilities_rejected(value):
    with pytest.raises(ValueError):
        validate_probabilities(value)
    with pytest.raises(ValueError):
        synthesis.ForecastOutput(probabilities=value, reasoning='Evidence is sufficient. 市場證據足夠。', abstain=False)


@pytest.mark.parametrize('field,value', [('status', 'resolved'), ('deadline', '2000-01-01T00:00:00Z'),
    ('open_price_confirmed', False), ('baseline_status', 'pending'), ('contract_symbol', None),
    ('dead_zone_pct', None), ('open_price', float('nan')), ('asset', 'ZN'),
    ('challenge_type', 'numeric'), ('prediction_schema', {'type': 'binary', 'outcomes': ['yes', 'no']})])
def test_unsupported_or_incomplete_challenges_rejected(challenge, field, value):
    challenge[field] = value
    with pytest.raises(ValueError):
        validate_challenge(challenge)


def test_explicit_schema_and_utc_legacy(challenge):
    challenge['prediction_schema'] = {'type': 'categorical_probabilities', 'outcomes': ['bearish', 'neutral', 'bullish']}
    challenge['deadline'] = challenge['deadline'].replace('+00:00', '')
    assert validate_challenge(challenge)['ticker'] == 'SPY'


@pytest.mark.parametrize('mutation', ['wrong_id', 'wrong_contract', 'stale', 'future', 'unready', 'baseline', 'delayed', 'no_quote'])
def test_bad_context_rejected(challenge, context, mutation):
    if mutation == 'wrong_id': context['challenge_id'] = 'other'
    if mutation == 'wrong_contract': context['contract_identity']['symbol'] = 'ESH7'
    if mutation == 'stale': context['quote']['as_of'] = (utc_now() - timedelta(minutes=16)).isoformat()
    if mutation == 'future': context['quote']['as_of'] = (utc_now() + timedelta(minutes=2)).isoformat()
    if mutation == 'unready': context['prediction_ready'] = False
    if mutation == 'baseline': context['baseline']['price'] = 5900
    if mutation == 'delayed': context['quote']['is_delayed'] = True
    if mutation == 'no_quote': context['quote'] = None
    with pytest.raises(ValueError): validate_context(context, challenge)


def test_synthesis_uses_question_and_real_round_table(monkeypatch, challenge, context, analysis):
    def llm(prompt, **kwargs):
        text = '\n'.join(m.content for m in prompt)
        assert 'ESZ6' in text and 'dead_zone_pct' in text and 'resolve_at' in text
        assert 'Mixed evidence discussed' in text and 'dissenting_opinions' in text
        assert 'proxy_limitations' in text
        kwargs['result_metadata'].update(model_provider='Gemini', model_name='actual-fallback')
        return synthesis.ForecastOutput(probabilities={'bearish': .2, 'neutral': .3, 'bullish': .5}, reasoning='Evidence supports mild upside, with uncertainty. 證據略為看漲，仍有不確定性。', abstain=False)
    monkeypatch.setattr(synthesis, 'call_llm', llm)
    result = synthesis.synthesize_forecast(challenge, context, analysis, 'SPY', ASSET_POLICIES['ES']['analysts'], 'primary', 'Groq')
    assert result['model_attribution']['model_name'] == 'actual-fallback'
    assert len(result['prompt_hash']) == 64
    assert result['probabilities']['bullish'] == .5  # hold was not mapped to neutral
    assert '證據略為看漲' in result['reasoning']
    assert result['evidence']['analysts']['technical_analyst']['confidence'] == .8


def test_synthesis_missing_evidence_does_not_call_model(monkeypatch, challenge, context):
    monkeypatch.setattr(synthesis, 'call_llm', lambda *a, **k: pytest.fail('must not call model'))
    with pytest.raises(ValueError):
        synthesis.synthesize_forecast(challenge, context, {}, 'SPY', ASSET_POLICIES['ES']['analysts'], 'primary', 'Groq')


def test_synthesis_both_models_failed_raises(monkeypatch, challenge, context, analysis):
    monkeypatch.setattr(synthesis, 'call_llm', lambda *a, **k: k['default_factory']())
    with pytest.raises(RuntimeError, match='primary and fallback'):
        synthesis.synthesize_forecast(challenge, context, analysis, 'SPY', ASSET_POLICIES['ES']['analysts'], 'primary', 'Groq')


def test_llm_actual_failover_metadata_and_no_silent_default(monkeypatch):
    from utils import llm
    from llm import models
    class Failing:
        def with_structured_output(self, *a, **k): return self
        def invoke(self, prompt): raise RuntimeError('offline')
    class Working(Failing):
        def invoke(self, prompt):
            return synthesis.ForecastOutput(probabilities={'bearish': .2, 'neutral': .3, 'bullish': .5}, reasoning='Evidence supports mild upside. 市場證據略為看漲。', abstain=False)
    monkeypatch.setattr(models, 'get_model', lambda *a: Failing())
    monkeypatch.setattr(models, 'get_fallback_model', lambda *a: Working())
    monkeypatch.setenv('FALLBACK_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/')
    monkeypatch.setenv('FALLBACK_MODEL', 'actual-fallback')
    metadata = {}
    llm.call_llm('test', 'primary', 'Groq', synthesis.ForecastOutput, default_factory=synthesis.forecast_unavailable, result_metadata=metadata)
    assert metadata == {'model_provider': 'Gemini', 'model_name': 'actual-fallback'}
    monkeypatch.setattr(models, 'get_fallback_model', lambda *a: Failing())
    with pytest.raises(RuntimeError, match='Forecast unavailable'):
        llm.call_llm('test', 'primary', 'Groq', synthesis.ForecastOutput, default_factory=synthesis.forecast_unavailable, result_metadata=metadata)
    assert metadata == {}


@pytest.fixture
def forecast(challenge):
    return {'challenge_id': challenge['id'], 'probabilities': {'bearish': .2, 'neutral': .3, 'bullish': .5},
            'reasoning': 'Evidence supports mild upside. 市場證據略為看漲。', 'prompt_hash': 'a' * 64,
            'model_attribution': {'model_provider': 'Groq', 'model_name': 'actual-model'}}


def test_remote_analysis_sends_selected_analysts_and_no_local_llm(monkeypatch, challenge, context, forecast):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return json.dumps({'forecast': forecast}).encode()
    def request(req, **kwargs):
        payload = json.loads(req.data)
        assert payload['selectedAnalysts'] == ASSET_POLICIES['ES']['analysts']
        assert 'analysts' not in payload
        assert payload['forecastChallenge'] == challenge
        assert payload['marketContext'] == context
        return Response()
    monkeypatch.setattr(cli.urllib.request, 'urlopen', request)
    assert cli.HedgeFundAPIClient().analyze('SPY', ASSET_POLICIES['ES']['analysts'], challenge, context) == forecast


def test_predict_sends_full_vector_attribution_and_hash(monkeypatch, forecast):
    client = cli.HeadlineArenaClient()
    def request(method, path, body, preflight=None):
        assert body['probabilities'] == forecast['probabilities']
        assert body['model_name'] == 'actual-model'
        assert body['prompt_hash'] == 'a' * 64
        assert 'confidence' not in body and 'direction' not in body
        return 201, {'counts_for_score': False}
    monkeypatch.setattr(client, 'authed_request', request)
    assert client.predict('id', forecast)[1]['counts_for_score'] is False


def test_authenticated_empty_list_does_not_broaden_scope(monkeypatch):
    client = cli.HeadlineArenaClient()
    monkeypatch.setattr(client, 'load_credentials', lambda: {'agent_id': 'agent', 'client_secret': 'placeholder'})
    monkeypatch.setattr(client, 'authed_request', lambda *a: (200, {'challenges': []}))
    monkeypatch.setattr(client, '_request', lambda *a: pytest.fail('must not broaden scope'))
    assert client.get_open_challenges() == []


@pytest.mark.parametrize('auth_status', [{}, {'agent_status': 'active_provisional', 'claim_pending': True}, {'agent_status': 'active', 'claim_pending': True}])
def test_unclaimed_or_unknown_status_blocks_submission(monkeypatch, auth_status):
    client = cli.HeadlineArenaClient()
    def token(**kwargs):
        client.auth_status = auth_status
        return 'placeholder'
    monkeypatch.setattr(client, 'get_token', token)
    with pytest.raises(ValueError, match='claim'): client.require_claimed()


@pytest.mark.parametrize('receipt,expected', [({'counts_for_score': True}, 'scored_eligible'), ({'counts_for_score': False}, 'paper_only'), ({}, 'unconfirmed')])
def test_submission_receipt_and_duplicate_guard(tmp_path, challenge, context, forecast, receipt, expected):
    journal = cli.ForecastJournal(tmp_path / 'runs.sqlite3')
    calls = []
    ha = SimpleNamespace(origin='https://example.invalid', load_credentials=lambda: {'agent_id': 'agent'},
                         challenge_context=lambda cid: context, require_claimed=lambda: None,
                         predict=lambda cid, f, **kw: (calls.append(cid) or 201, receipt))
    hedge = SimpleNamespace(analyze=lambda *a: forecast)
    assert cli.process_challenge(ha, hedge, journal, challenge, True) == expected
    with pytest.raises(ValueError, match='Already attempted'):
        cli.process_challenge(ha, hedge, journal, challenge, True)
    assert len(calls) == 1
    data = json.loads(journal.db.execute('SELECT payload FROM runs').fetchone()[0])
    assert data['forecast']['probabilities'] == forecast['probabilities']
    assert set(data['benchmarks']) == {'uniform', 'always_neutral', 'momentum'}


def test_dry_run_does_not_reserve_and_pending_attempt_is_not_replayed(tmp_path, challenge, context, forecast):
    journal = cli.ForecastJournal(tmp_path / 'runs.sqlite3')
    def timeout(*a, **kw): raise TimeoutError('response lost')
    ha = SimpleNamespace(origin='https://example.invalid', load_credentials=lambda: {'agent_id': 'agent'},
                         challenge_context=lambda cid: context, require_claimed=lambda: None, predict=timeout)
    hedge = SimpleNamespace(analyze=lambda *a: forecast)
    assert cli.process_challenge(ha, hedge, journal, challenge) == 'dry_run'
    assert not journal.attempted(ha.origin, 'agent', challenge['id'])
    with pytest.raises(TimeoutError): cli.process_challenge(ha, hedge, journal, challenge, True)
    with pytest.raises(ValueError, match='Already attempted'): cli.process_challenge(ha, hedge, journal, challenge, True)


def test_deadline_rechecked_after_analysis(tmp_path, challenge, context, forecast):
    def analyze(*a):
        challenge['deadline'] = '2000-01-01T00:00:00Z'
        return forecast
    ha = SimpleNamespace(origin='https://example.invalid', load_credentials=lambda: {'agent_id': 'agent'},
                         challenge_context=lambda cid: context, predict=lambda *a: pytest.fail('expired submission'))
    with pytest.raises(ValueError, match='deadline'):
        cli.process_challenge(ha, SimpleNamespace(analyze=analyze), cli.ForecastJournal(tmp_path / 'runs.sqlite3'), challenge, True)


def test_brier_and_momentum_neutral_boundary(challenge, context):
    context['quote']['price'] = challenge['open_price'] * (1 + challenge['dead_zone_pct'] / 100)
    vectors = cli.benchmark_vectors(challenge, context)
    assert vectors['momentum']['neutral'] == 1
    assert cli.brier_score(vectors['always_neutral'], 'neutral') == 0
    assert cli.brier_score(vectors['uniform'], 'bullish') == pytest.approx(2/3)


def test_cli_works_without_site_packages():
    result = subprocess.run([sys.executable, '-S', str(ROOT / 'scripts/sync_headline_arena.py'), '--help'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '--evaluate' in result.stdout


def test_forecast_api_validates_before_work(monkeypatch, challenge, context):
    import webui2
    monkeypatch.setattr(webui2, 'resolve_ticker', lambda t: t)
    monkeypatch.setattr(webui2, 'run_hedge_fund', lambda **k: pytest.fail('must validate before analysis'))
    response = webui2.app.test_client().post('/api/analysis', json={
        'tickers': 'SPY', 'analysts': ASSET_POLICIES['ES']['analysts'],
        'forecastChallenge': challenge, 'marketContext': context, 'enableRoundTable': True})
    assert response.status_code == 400
    assert 'selectedAnalysts' in response.get_json()['error']


def test_forecast_api_returns_synthesis_without_discord(monkeypatch, challenge, context, analysis, forecast):
    import webui2
    monkeypatch.setattr(webui2, 'resolve_ticker', lambda t: t)
    def run(**kwargs):
        assert kwargs['selected_analysts'] == ASSET_POLICIES['ES']['analysts']
        return copy.deepcopy(analysis)
    monkeypatch.setattr(webui2, 'run_hedge_fund', run)
    monkeypatch.setattr(webui2, 'synthesize_forecast', lambda *a: forecast)
    monkeypatch.setattr(webui2, 'send_discord_notification', lambda *a: pytest.fail('no forecast notification'))
    response = webui2.app.test_client().post('/api/analysis', json={
        'tickers': 'SPY', 'selectedAnalysts': ASSET_POLICIES['ES']['analysts'],
        'forecastChallenge': challenge, 'marketContext': context, 'enableRoundTable': True})
    assert response.status_code == 200
    assert response.get_json()['forecast'] == forecast


def test_no_news_default_is_not_usable_evidence(monkeypatch, challenge, context, analysis):
    analysis['analyst_signals']['sentiment_agent']['SPY']['data_coverage']['news_count'] = 0
    monkeypatch.setattr(synthesis, 'call_llm', lambda *a, **k: pytest.fail('no evidence'))
    with pytest.raises(ValueError, match='news evidence'):
        synthesis.synthesize_forecast(challenge, context, analysis, 'SPY', ASSET_POLICIES['ES']['analysts'], 'primary', 'Groq')


def test_synthesis_abstains_and_rejects_monolingual_reasoning(monkeypatch, challenge, context, analysis):
    for abstain, reasoning in [(True, 'Evidence is inadequate. 市場證據不足。'), (False, 'Evidence supports mild upside but uncertainty remains.')]:
        def model(*a, **k):
            return synthesis.ForecastOutput(probabilities={'bearish': .2, 'neutral': .3, 'bullish': .5}, reasoning=reasoning, abstain=abstain)
        monkeypatch.setattr(synthesis, 'call_llm', model)
        with pytest.raises(ValueError):
            synthesis.synthesize_forecast(challenge, context, analysis, 'SPY', ASSET_POLICIES['ES']['analysts'], 'primary', 'Groq')


def test_journal_reservation_is_unique_across_connections(tmp_path):
    path = tmp_path / 'runs.sqlite3'
    first, second = cli.ForecastJournal(path), cli.ForecastJournal(path)
    run_id = first.record('origin', 'agent', 'question', 'prepared', {})
    first.reserve('origin', 'agent', 'question', run_id)
    with pytest.raises(ValueError, match='already exists'):
        second.reserve('origin', 'agent', 'question', run_id)


def test_evaluation_excludes_paper_and_uses_same_questions(tmp_path, forecast, challenge, context):
    journal = cli.ForecastJournal(tmp_path / 'runs.sqlite3')
    payload = {'forecast': forecast, 'benchmarks': cli.benchmark_vectors(challenge, context)}
    for eligible in (True, False):
        run = journal.record('origin', 'agent', 'question', 'prepared', payload)
        journal.finish(run, 201, {'counts_for_score': eligible})
    calls = []
    def get(*a):
        calls.append(a)
        return 200, {'status': 'resolved', 'result': 'bullish'}
    result = journal.evaluate(SimpleNamespace(origin='origin', authed_request=get, load_credentials=lambda: {'agent_id': 'agent'}))
    assert result['settled_comparable_forecasts'] == 1
    assert len(calls) == 1
    assert result['mean_brier']['committee'] == pytest.approx(.38)
    assert result['mean_brier']['uniform'] == pytest.approx(2/3)
    assert result['mean_brier']['always_neutral'] == 2


def test_primary_malformed_output_uses_fallback(monkeypatch):
    from utils import llm
    from llm import models
    class Malformed:
        def with_structured_output(self, *a, **k): return self
        def invoke(self, prompt): return SimpleNamespace(content='not json')
    class Fallback(Malformed):
        def invoke(self, prompt):
            return synthesis.ForecastOutput(probabilities={'bearish': .2, 'neutral': .3, 'bullish': .5}, reasoning='Evidence supports mild upside. 市場證據略為看漲。', abstain=False)
    monkeypatch.setattr(models, 'get_model', lambda *a: Malformed())
    monkeypatch.setattr(models, 'get_fallback_model', lambda *a: Fallback())
    metadata = {}
    result = llm.call_llm('test', 'primary', 'Groq', synthesis.ForecastOutput, default_factory=synthesis.forecast_unavailable, result_metadata=metadata)
    assert result.probabilities['bullish'] == .5
    assert metadata['model_name'] != 'primary'


def test_forecast_async_is_rejected(monkeypatch, challenge, context):
    import webui2
    monkeypatch.setattr(webui2, 'resolve_ticker', lambda t: t)
    response = webui2.app.test_client().post('/api/analysis/async', json={
        'tickers': 'SPY', 'selectedAnalysts': ASSET_POLICIES['ES']['analysts'],
        'forecastChallenge': challenge, 'marketContext': context, 'enableRoundTable': True})
    assert response.status_code == 400
    assert 'synchronous' in response.get_json()['error']


def test_prediction_401_refresh_rechecks_claim_status(monkeypatch, forecast):
    client = cli.HeadlineArenaClient()
    monkeypatch.setattr(client, 'load_credentials', lambda: {'agent_id': 'agent'})
    calls = []
    def token(force=False):
        client.auth_status = {'agent_status': 'active_provisional' if force else 'active', 'claim_pending': force}
        return 'placeholder'
    monkeypatch.setattr(client, 'get_token', token)
    monkeypatch.setattr(client, '_request', lambda *a, **k: (calls.append(a) or 401, {}))
    with pytest.raises(ValueError, match='claim'):
        client.predict('question', forecast)
    assert len(calls) == 1


def test_prediction_401_retry_runs_preflight_again(monkeypatch, forecast):
    client = cli.HeadlineArenaClient()
    monkeypatch.setattr(client, 'load_credentials', lambda: {'agent_id': 'agent'})
    def token(force=False):
        client.auth_status = {'agent_status': 'active', 'claim_pending': False}
        return 'placeholder'
    monkeypatch.setattr(client, 'get_token', token)
    requests, checks = [], []
    monkeypatch.setattr(client, '_request', lambda *a, **k: (requests.append(a) or 401, {}))
    def preflight():
        checks.append(1)
        if len(checks) == 2: raise ValueError('Quote expired during refresh')
    with pytest.raises(ValueError, match='expired'):
        client.predict('question', forecast, preflight=preflight)
    assert len(requests) == 1 and len(checks) == 2


def test_atomic_credential_store_preserves_other_agents_and_private_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, 'CRED_DIR', tmp_path)
    monkeypatch.setattr(cli, 'CRED_FILE', tmp_path / 'credentials.json')
    client = cli.HeadlineArenaClient()
    client.save_credentials({'agent_id': 'one', 'claim_pending': True})
    client.save_credentials({'agent_id': 'two'})
    client.save_credentials({'agent_id': 'one', 'auth_status': {'agent_status': 'active'}})
    saved = json.loads(cli.CRED_FILE.read_text())[client.origin]['_agents']
    assert set(saved) == {'one', 'two'}
    assert saved['one']['claim_pending'] is True
    assert cli.CRED_FILE.stat().st_mode & 0o777 == 0o600
    cli.CRED_FILE.write_text('invalid json')
    with pytest.raises(ValueError): client.save_credentials({'agent_id': 'three'})
    assert cli.CRED_FILE.read_text() == 'invalid json'


def test_missing_delay_flag_and_non_daily_legacy_schema_rejected(challenge, context):
    context['quote'].pop('is_delayed')
    with pytest.raises(ValueError, match='delayed'): validate_context(context, challenge)
    challenge['challenge_type'] = 'flash'
    with pytest.raises(ValueError, match='explicit'): validate_challenge(challenge)


def test_momentum_uses_prices_when_derived_change_is_absent(challenge, context):
    context.pop('change_from_baseline_pct')
    context['quote']['price'] = challenge['open_price'] * 1.01
    assert cli.benchmark_vectors(challenge, context)['momentum']['bullish'] == 1


def test_concurrent_credential_updates_preserve_every_agent(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(cli, 'CRED_DIR', tmp_path)
    monkeypatch.setattr(cli, 'CRED_FILE', tmp_path / 'credentials.json')
    def update(number):
        cli.HeadlineArenaClient().save_credentials({'agent_id': str(number)})
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(update, range(12)))
    saved = json.loads(cli.CRED_FILE.read_text())[cli.DEFAULT_HA_ORIGIN]['_agents']
    assert set(saved) == {str(n) for n in range(12)}


def test_evaluation_filters_other_agents(tmp_path, forecast, challenge, context):
    journal = cli.ForecastJournal(tmp_path / 'runs.sqlite3')
    payload = {'forecast': forecast, 'benchmarks': cli.benchmark_vectors(challenge, context)}
    for agent in ['selected', 'other']:
        run_id = journal.record('origin', agent, 'question', 'prepared', payload)
        journal.finish(run_id, 201, {'counts_for_score': True})
    client = SimpleNamespace(origin='origin', load_credentials=lambda: {'agent_id': 'selected'},
                             authed_request=lambda *a: (200, {'status': 'resolved', 'result': 'bullish'}))
    assert journal.evaluate(client)['settled_comparable_forecasts'] == 1


def test_processing_limit_continues_past_skipped_challenges(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, 'CRED_DIR', tmp_path)
    ha = SimpleNamespace(origin='origin', load_credentials=lambda: {},
                         get_open_challenges=lambda **kw: [{'id': str(n)} for n in range(3)])
    monkeypatch.setattr(cli, 'HeadlineArenaClient', lambda **kw: ha)
    monkeypatch.setattr(cli, 'HedgeFundAPIClient', lambda **kw: object())
    processed = []
    def process(*args, **kwargs):
        question = args[3]['id']
        processed.append(question)
        if question != '2': raise ValueError('no usable evidence')
        return 'dry_run'
    monkeypatch.setattr(cli, 'process_challenge', process)
    monkeypatch.setattr(sys, 'argv', ['sync_headline_arena.py', '--dry-run', '--limit', '1'])
    cli.main()
    assert processed == ['0', '1', '2']


def test_confirmed_unsent_attempt_releases_reservation(tmp_path, challenge, context, forecast):
    journal = cli.ForecastJournal(tmp_path / 'runs.sqlite3')
    def unsent(*a, **kw): raise cli.PredictionNotSent('Quote expired before POST')
    ha = SimpleNamespace(origin='origin', load_credentials=lambda: {'agent_id': 'agent'},
                         challenge_context=lambda cid: context, require_claimed=lambda: None, predict=unsent)
    with pytest.raises(cli.PredictionNotSent):
        cli.process_challenge(ha, SimpleNamespace(analyze=lambda *a: forecast), journal, challenge, True)
    assert not journal.attempted('origin', 'agent', challenge['id'])
    assert journal.db.execute('SELECT state FROM runs').fetchone()[0] == 'not_sent'


def test_refresh_only_patches_token_fields_preserving_concurrent_claim(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, 'CRED_DIR', tmp_path)
    monkeypatch.setattr(cli, 'CRED_FILE', tmp_path / 'credentials.json')
    monkeypatch.delenv('HA_AGENT_ID', raising=False)
    monkeypatch.delenv('HA_CLIENT_SECRET', raising=False)
    client = cli.HeadlineArenaClient()
    client.save_credentials({'agent_id': 'agent', 'client_secret': 'your_api_key_here', 'claim_note': 'old'})
    def refresh(*a, **kw):
        client.save_credentials({'agent_id': 'agent', 'claim_note': 'new claim details'})
        return 200, {'access_token': 'your_api_key_here', 'expires_in': 600, 'agent_status': 'active', 'claim_pending': False}
    monkeypatch.setattr(client, '_request', refresh)
    assert client.get_token(force=True)
    assert client.load_credentials()['claim_note'] == 'new claim details'


def test_explicit_direction_only_schema_is_not_submitted_as_probabilities(challenge):
    challenge['prediction_schema'] = {'input_encoding': 'direction_confidence', 'outcomes': ['bearish', 'neutral', 'bullish']}
    with pytest.raises(ValueError, match='encoding'): validate_challenge(challenge)


def test_observed_all_neutral_news_with_zero_directional_confidence_is_valid(analysis):
    signal = analysis['analyst_signals']['sentiment_agent']['SPY']
    signal.update(signal='neutral', confidence=0)
    evidence = analyst_evidence(analysis, 'SPY', ['sentiment_analyst'])
    assert evidence['sentiment_analyst']['confidence'] == 0
    signal['data_coverage']['news_count'] = 0
    with pytest.raises(ValueError): analyst_evidence(analysis, 'SPY', ['sentiment_analyst'])


@pytest.mark.parametrize('status,state,released', [(400, 'rejected', True), (422, 'rejected', True),
    (429, 'rejected', True), (409, 'remote_conflict', False), (408, 'unconfirmed', False), (500, 'unconfirmed', False)])
def test_rejection_vs_ambiguous_attempts(tmp_path, status, state, released):
    journal = cli.ForecastJournal(tmp_path / 'runs.sqlite3')
    run = journal.record('origin', 'agent', 'question', 'prepared', {})
    journal.reserve('origin', 'agent', 'question', run)
    assert journal.finish(run, status, {}) == state
    assert journal.attempted('origin', 'agent', 'question') is not released


def test_evaluation_reports_failed_reads(tmp_path, forecast, challenge, context):
    journal = cli.ForecastJournal(tmp_path / 'runs.sqlite3')
    run = journal.record('origin', 'agent', 'question', 'prepared', {'forecast': forecast, 'benchmarks': cli.benchmark_vectors(challenge, context)})
    journal.finish(run, 201, {'counts_for_score': True})
    client = SimpleNamespace(origin='origin', load_credentials=lambda: {'agent_id': 'agent'},
                             authed_request=lambda *a: (403, {}))
    result = journal.evaluate(client)
    assert result['fetch_or_data_failures'] == [{'challenge_id': 'question', 'http_status': 403}]


def test_env_secret_is_not_persisted_by_token_refresh(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, 'CRED_DIR', tmp_path)
    monkeypatch.setattr(cli, 'CRED_FILE', tmp_path / 'credentials.json')
    monkeypatch.setenv('HA_AGENT_ID', 'agent')
    monkeypatch.setenv('HA_CLIENT_SECRET', 'your_api_key_here')
    client = cli.HeadlineArenaClient()
    monkeypatch.setattr(client, '_request', lambda *a, **k: (200, {
        'access_token': 'your_api_key_here', 'expires_in': 600, 'agent_status': 'active', 'claim_pending': False}))
    assert client.get_token(force=True)
    saved = json.loads(cli.CRED_FILE.read_text())[client.origin]['_agents']['agent']
    assert 'client_secret' not in saved


def test_bilingual_injection_does_not_mutate_original_prompt():
    from utils.llm import inject_bilingual_instruction
    from langchain_core.messages import HumanMessage
    prompt = [HumanMessage(content='Evidence')]
    expected = inject_bilingual_instruction(prompt)
    actual = inject_bilingual_instruction(prompt)
    assert len(prompt) == 1
    assert len(actual) == 2
    assert [m.content for m in actual] == [m.content for m in expected]


def test_api_forecast_model_outage_returns_503(monkeypatch, challenge, context, analysis):
    import webui2
    monkeypatch.setattr(webui2, 'resolve_ticker', lambda t: t)
    monkeypatch.setattr(webui2, 'run_hedge_fund', lambda **k: copy.deepcopy(analysis))
    monkeypatch.setattr(webui2, 'synthesize_forecast', lambda *a: synthesis.forecast_unavailable())
    response = webui2.app.test_client().post('/api/analysis', json={
        'tickers': 'SPY', 'selectedAnalysts': ASSET_POLICIES['ES']['analysts'],
        'forecastChallenge': challenge, 'marketContext': context, 'enableRoundTable': True})
    assert response.status_code == 503
    assert 'forecast' not in response.get_json()
