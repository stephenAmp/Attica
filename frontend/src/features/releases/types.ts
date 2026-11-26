export interface ReleaseFilters {
    baseline_release: string
    candidate_release: string
    feature: string
    environment: string
    start_time: string
    end_time: string
}

export interface ReleaseMetrics {
    trace_count: number
    call_count: number 
    trace_with_failed_calls: number
    failed_call_trace_rate:  number | null
    calls_per_trace: number | null
    input_tokens_per_trace: number | null
    output_tokens_per_trace: number | null
    input_tokens_per_call: number | null
    output_tokens_per_call: number | null
}


export type ReleaseMetricChange = Omit<ReleaseMetrics, "failed_call_trace_rate"> & {failed_call_trace_rate_pp: number | null}


export interface TraceDrilldown {
  release: string
  feature: string
  environment: string
  start_time: string
  end_time: string
  has_error: boolean
  cohort: "release" 
}


export interface ReleaseComparison {
  tenant_id: string;
  baseline_release: string;
  candidate_release: string;

  baseline: ReleaseMetrics;
  candidate: ReleaseMetrics;
  change: ReleaseMetricChange;

  excluded_ambiguous_traces: number;

  baseline_drilldown: TraceDrilldown;
  candidate_drilldown: TraceDrilldown;
}