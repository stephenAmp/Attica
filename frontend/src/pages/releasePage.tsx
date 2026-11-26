import { useParams, useSearchParams } from "react-router-dom"
import { useReleaseComparison } from "../features/releases/useReleaseComparison";
import type { ReleaseFilters } from "../features/releases/types";


export default function ReleasesPage(){
    const { tenantId = "" } = useParams();
    const [searchParams, setSearchParams] = useSearchParams();

    const filters: ReleaseFilters = {
        feature: searchParams.get("feature") ?? "",
        environment: searchParams.get("environment") ?? "",
        baseline_release: searchParams.get("baseline_release") ?? "",
        candidate_release: searchParams.get("candidate_release") ?? "",
        start_time: searchParams.get("start_time") ?? "",
        end_time: searchParams.get("end_time") ?? "",
    };

    const comparison = useReleaseComparison(tenantId, filters);

    return(
       <div>
            <h1>Release Comparison</h1>
        </div>
    )
}