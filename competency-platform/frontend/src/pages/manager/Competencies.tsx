/**
 * Competency list page — CompetencyList with status badges, CompetencyCreateButton.
 * From §10.2: /competencies route.
 */
import { useQuery } from "@tanstack/react-query";
import { competencyApi } from "@/api/competencies";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Plus } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  active: "default",
  under_review: "secondary",
  draft: "outline",
  deprecated: "destructive",
};

export default function Competencies() {
  const navigate = useNavigate();
  const { data: competencies, isLoading } = useQuery({
    queryKey: ["competencies"],
    queryFn: competencyApi.list,
  });

  return (
    <div className="space-y-6 animate-scale-in">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Competencies</h1>
        <Button onClick={() => navigate("/competencies/new")}>
          <Plus className="mr-2 h-4 w-4" /> Create Competency
        </Button>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading competencies…</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {competencies?.map((comp) => (
            <Link key={comp.id} to={`/competencies/${comp.id}`}>
              <Card className="h-full cursor-pointer transition-all hover:border-primary/50 hover:shadow-lg">
                <CardContent className="pt-6 flex flex-col justify-between h-full space-y-3">
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="font-semibold text-lg leading-snug">{comp.name}</h3>
                      <Badge variant={STATUS_VARIANT[comp.status] ?? "outline"}>
                        {comp.status}
                      </Badge>
                    </div>
                    <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                      {comp.description}
                    </p>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-muted-foreground border-t pt-3">
                    <span>v{comp.version_major ?? 1}.{comp.version_minor ?? 0}</span>
                    {comp.decomp_confidence != null && (
                      <span>AI Confidence: {(comp.decomp_confidence * 100).toFixed(0)}%</span>
                    )}
                    {comp.target_roles && (
                      <span className="truncate">{comp.target_roles.join(", ")}</span>
                    )}
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
