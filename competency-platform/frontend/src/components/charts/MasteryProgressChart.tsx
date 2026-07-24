/**
 * Line chart showing mastery progression over time.
 * From §10.2: EmployeeDetail includes MasteryProgressChart.
 */
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DataPoint {
  date: string;
  mastery_level: number;
  score: number;
}

interface MasteryProgressChartProps {
  data: DataPoint[];
  title?: string;
}

export function MasteryProgressChart({
  data,
  title = "Mastery Progress",
}: MasteryProgressChartProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis dataKey="date" className="text-xs" />
            <YAxis domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} className="text-xs" />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "var(--radius)",
              }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="mastery_level"
              stroke="hsl(var(--primary))"
              strokeWidth={2}
              name="Mastery Level"
              dot={{ r: 4 }}
            />
            <Line
              type="monotone"
              dataKey="score"
              stroke="hsl(var(--chart-2))"
              strokeWidth={1}
              strokeDasharray="5 5"
              name="Assessment Score"
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
