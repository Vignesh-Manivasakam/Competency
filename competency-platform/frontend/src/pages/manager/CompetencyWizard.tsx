/**
 * 4-step competency creation wizard.
 * From §10.2: /competencies/new
 *   Step 1: Definition form
 *   Step 2: AI decompose trigger + spinner
 *   Step 3: DAG review (react-flow preview)
 *   Step 4: Validation / approve
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { competencyApi, type Competency } from "@/api/competencies";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, CheckCircle2, ArrowRight, ArrowLeft } from "lucide-react";

// Zod schema for Step 1 — definition form
const competencySchema = z.object({
  name: z.string().min(3, "Name must be at least 3 characters"),
  description: z.string().min(10, "Description must be at least 10 characters"),
  business_relevance: z.string().min(5, "Explain why this competency matters"),
  target_roles: z.string().min(1, "Enter at least one role"),
  industry_context: z.string().optional(),
  max_depth: z.number().min(1).max(5).default(3),
});

type FormValues = z.infer<typeof competencySchema>;

const STEPS = ["Definition", "AI Decomposition", "DAG Review", "Validation"] as const;

export default function CompetencyWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [competency, setCompetency] = useState<Competency | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [decompStatus, setDecompStatus] = useState<string>("idle");

  const form = useForm<FormValues>({
    resolver: zodResolver(competencySchema),
    defaultValues: { max_depth: 3 },
  });

  // Step 1 → Create competency
  const createMutation = useMutation({
    mutationFn: (values: FormValues) =>
      competencyApi.create({
        name: values.name,
        description: values.description,
        business_relevance: values.business_relevance,
        target_roles: values.target_roles.split(",").map((r) => r.trim()),
      }),
    onSuccess: (data) => {
      setCompetency(data);
      setStep(1);
    },
  });

  // Step 2 → Trigger AI decomposition + poll (§21.1 Flow 1)
  const decomposeMutation = useMutation({
    mutationFn: async () => {
      if (!competency) throw new Error("No competency");
      const values = form.getValues();
      const { job_id } = await competencyApi.triggerDecompose(competency.id, {
        industry_context: values.industry_context,
        max_depth: values.max_depth,
      });
      setJobId(job_id);
      setDecompStatus("running");

      // Poll every 3 seconds until done
      let result = { status: "running" as string };
      while (result.status === "running") {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        result = await competencyApi.pollDecompose(competency.id, job_id);
      }

      setDecompStatus(result.status);
      if (result.status === "failed") {
        throw new Error("Decomposition failed");
      }
      return result;
    },
    onSuccess: () => setStep(2),
  });

  // Step 4 → Validate
  const validateMutation = useMutation({
    mutationFn: () => {
      if (!competency) throw new Error("No competency");
      return competencyApi.validate(competency.id, {
        approved_nodes: [],  // All approved in simple flow
        removed_nodes: [],
      });
    },
    onSuccess: () => {
      if (competency) navigate(`/competencies/${competency.id}`);
    },
  });

  return (
    <div className="mx-auto max-w-2xl space-y-6 animate-scale-in">
      <h1 className="text-2xl font-bold tracking-tight">Create Competency</h1>

      {/* Step indicator */}
      <div className="flex items-center justify-between border-b pb-4">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-medium transition-colors ${
                i <= step
                  ? "bg-primary text-primary-foreground shadow"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {i < step ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
            </div>
            <span className="text-sm font-medium hidden sm:inline">{label}</span>
            {i < STEPS.length - 1 && <ArrowRight className="h-4 w-4 text-muted-foreground hidden sm:inline" />}
          </div>
        ))}
      </div>

      {/* Step 1: Definition Form */}
      {step === 0 && (
        <Card>
          <CardHeader><CardTitle>Competency Definition</CardTitle></CardHeader>
          <CardContent>
            <form
              onSubmit={form.handleSubmit((v) => createMutation.mutate(v))}
              className="space-y-4"
            >
              <div>
                <Label>Name</Label>
                <Input {...form.register("name")} placeholder="e.g. Cloud Architecture" />
                {form.formState.errors.name && (
                  <p className="mt-1 text-xs text-destructive">{form.formState.errors.name.message}</p>
                )}
              </div>
              <div>
                <Label>Description</Label>
                <Textarea {...form.register("description")} rows={3} placeholder="Detailed description of competency goals..." />
                {form.formState.errors.description && (
                  <p className="mt-1 text-xs text-destructive">{form.formState.errors.description.message}</p>
                )}
              </div>
              <div>
                <Label>Business Relevance</Label>
                <Textarea {...form.register("business_relevance")} rows={2} placeholder="Why is this competency critical for organizational success?" />
              </div>
              <div>
                <Label>Target Roles (comma-separated)</Label>
                <Input {...form.register("target_roles")} placeholder="Backend Engineer, DevOps, Solutions Architect" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Industry Context</Label>
                  <Input {...form.register("industry_context")} placeholder="e.g. fintech, healthcare" />
                </div>
                <div>
                  <Label>Max Depth (1-5)</Label>
                  <Input type="number" {...form.register("max_depth", { valueAsNumber: true })} />
                </div>
              </div>
              <Button type="submit" disabled={createMutation.isPending} className="w-full">
                {createMutation.isPending ? "Creating…" : "Create & Continue"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Step 2: AI Decomposition — trigger + spinner */}
      {step === 1 && (
        <Card>
          <CardHeader><CardTitle>AI Skill Decomposition</CardTitle></CardHeader>
          <CardContent className="flex flex-col items-center gap-4 py-8">
            {decompStatus === "idle" || decompStatus === "running" ? (
              <>
                {decomposeMutation.isPending ? (
                  <>
                    <Loader2 className="h-12 w-12 animate-spin text-primary" />
                    <p className="text-muted-foreground font-medium">
                      AI is decomposing "{competency?.name}" into skills…
                    </p>
                    <p className="text-xs text-muted-foreground font-mono">
                      Job ID: {jobId ?? "starting…"}
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-center text-muted-foreground">
                      Ready to trigger AI decomposition for "{competency?.name}".
                    </p>
                    <Button onClick={() => decomposeMutation.mutate()}>
                      Start AI Decomposition
                    </Button>
                  </>
                )}
              </>
            ) : decompStatus === "failed" ? (
              <>
                <p className="text-destructive font-medium">Decomposition failed. Please retry.</p>
                <Button variant="outline" onClick={() => decomposeMutation.mutate()}>
                  Retry Decomposition
                </Button>
              </>
            ) : null}
          </CardContent>
        </Card>
      )}

      {/* Step 3: DAG Review (simplified — full editor on detail page) */}
      {step === 2 && (
        <Card>
          <CardHeader><CardTitle>Review Skill DAG</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              The AI has generated a skill graph for "{competency?.name}".
              You can review and edit the full DAG on the competency detail page after validation.
            </p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(1)}>
                <ArrowLeft className="mr-1 h-3 w-3" /> Re-Decompose
              </Button>
              <Button onClick={() => setStep(3)}>
                Approve & Continue <ArrowRight className="ml-1 h-3 w-3" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 4: Validation */}
      {step === 3 && (
        <Card>
          <CardHeader><CardTitle>Validate & Activate</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Confirm to activate this competency. The skill graph will be locked and
              employees can begin their learning paths.
            </p>
            <Button
              onClick={() => validateMutation.mutate()}
              disabled={validateMutation.isPending}
              className="w-full"
            >
              {validateMutation.isPending ? "Validating…" : "Validate & Activate"}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
