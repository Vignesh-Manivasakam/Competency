/**
 * Employee list — EmployeeTable with mastery level chips, filter by skill gap.
 * From §10.2: /employees route.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { employeeApi } from "@/api/employees";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Link } from "react-router-dom";

const LEVEL_LABELS = ["N/A", "Aware", "Dev", "Prof", "Adv", "Master"];

export default function Employees() {
  const [search, setSearch] = useState("");
  const [showGapsOnly, setShowGapsOnly] = useState(false);

  const { data: employees, isLoading } = useQuery({
    queryKey: ["employees", { skill_gap: showGapsOnly }],
    queryFn: () => employeeApi.list({ skill_gap: showGapsOnly || undefined }),
  });

  const filtered = employees?.filter((e) =>
    e.full_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6 animate-scale-in">
      <h1 className="text-2xl font-bold tracking-tight">Employees</h1>

      <div className="flex items-center gap-4">
        <Input
          placeholder="Search employees…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <div className="flex items-center gap-2">
          <Switch
            id="gap-filter"
            checked={showGapsOnly}
            onCheckedChange={setShowGapsOnly}
          />
          <Label htmlFor="gap-filter">Show skill gaps only</Label>
        </div>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading employees…</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Competencies</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered?.map((emp) => (
              <TableRow key={emp.id}>
                <TableCell>
                  <Link
                    to={`/employees/${emp.id}`}
                    className="font-medium text-primary hover:underline"
                  >
                    {emp.full_name}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground">{emp.email}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {emp.competencies?.map((c) => (
                      <Badge
                        key={c.competency_id}
                        variant="outline"
                        className="text-xs"
                        title={c.competency_name}
                      >
                        {c.competency_name}: {LEVEL_LABELS[c.mastery_level] ?? "N/A"}
                      </Badge>
                    ))}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
