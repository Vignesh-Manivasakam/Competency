/**
 * PendingReviewsList + MasteryOverrideModal.
 * From §10.2: /reviews route — competencies awaiting manager validation; mastery overrides.
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { dashboardApi } from "@/api/dashboard";
import { competencyApi } from "@/api/competencies";
import { employeeApi } from "@/api/employees";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { CheckCircle, XCircle } from "lucide-react";

interface PendingReview {
  competency_id: string;
  competency_name: string;
  status: string;
  created_at: string;
  skill_count: number;
}

export default function Reviews() {
  const queryClient = useQueryClient();
  const [overrideModal, setOverrideModal] = useState<{
    open: boolean;
    employeeId: string;
    skillId: string;
    skillName: string;
  }>({ open: false, employeeId: "", skillId: "", skillName: "" });
  const [overrideLevel, setOverrideLevel] = useState(0);
  const [overrideReason, setOverrideReason] = useState("");

  const { data: reviews } = useQuery({
    queryKey: ["dashboard", "pending-reviews"],
    queryFn: dashboardApi.getPendingReviews,
  });

  // Approve competency mutation
  const approveMutation = useMutation({
    mutationFn: (compId: string) =>
      competencyApi.validate(compId, { approved_nodes: [], removed_nodes: [] }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["dashboard", "pending-reviews"] }),
  });

  // Mastery override mutation
  const overrideMutation = useMutation({
    mutationFn: () =>
      employeeApi.overrideMastery(overrideModal.employeeId, {
        skill_id: overrideModal.skillId,
        new_level: overrideLevel,
        reason: overrideReason,
      }),
    onSuccess: () => {
      setOverrideModal({ open: false, employeeId: "", skillId: "", skillName: "" });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const pendingList = (reviews ?? []) as unknown as PendingReview[];

  return (
    <div className="space-y-6 animate-scale-in">
      <h1 className="text-2xl font-bold tracking-tight">Pending Reviews</h1>

      {/* PendingReviewsList */}
      {pendingList.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No pending reviews. All competencies are up to date.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {pendingList.map((review) => (
            <Card key={review.competency_id}>
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <h3 className="font-semibold">{review.competency_name}</h3>
                  <p className="text-sm text-muted-foreground">
                    {review.skill_count} skills · Created{" "}
                    {new Date(review.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{review.status}</Badge>
                  <Button
                    size="sm"
                    onClick={() => approveMutation.mutate(review.competency_id)}
                    disabled={approveMutation.isPending}
                  >
                    <CheckCircle className="mr-1 h-3 w-3" /> Approve
                  </Button>
                  <Button size="sm" variant="ghost">
                    <XCircle className="mr-1 h-3 w-3" /> Reject
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* MasteryOverrideModal */}
      <Dialog
        open={overrideModal.open}
        onOpenChange={(open) =>
          setOverrideModal((prev) => ({ ...prev, open }))
        }
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Override Mastery Level</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Override mastery for: <strong>{overrideModal.skillName}</strong>
            </p>
            <div>
              <Label>New Mastery Level (0-5)</Label>
              <Input
                type="number"
                min={0}
                max={5}
                value={overrideLevel}
                onChange={(e) => setOverrideLevel(Number(e.target.value))}
              />
            </div>
            <div>
              <Label>Reason</Label>
              <Textarea
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Explain why this override is needed…"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOverrideModal((p) => ({ ...p, open: false }))}>
              Cancel
            </Button>
            <Button
              onClick={() => overrideMutation.mutate()}
              disabled={overrideMutation.isPending || !overrideReason}
            >
              {overrideMutation.isPending ? "Saving…" : "Apply Override"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
