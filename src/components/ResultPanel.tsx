import { useState } from 'react';
import {
  CheckCircle2, Save, FolderOpen, FileOutput, Copy, Check,
  Music, Clock, Layers, Gauge,
} from 'lucide-react';
import {
  Card, CardHeader, CardTitle, CardContent, CardFooter,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { useLanguage } from '@/i18n/LanguageContext';
import { TRANSLATIONS } from '@/i18n/translations';
import { selectSaveLocation, showInFolder, copyFile } from '@/lib/tauri';
import type { ConversionResult, NbtExportConfig } from '@/types/conversion';

interface ResultPanelProps {
  result: ConversionResult;
  onExportNbt?: () => void;
  onReset?: () => void;
}

export function ResultPanel({ result, onExportNbt, onReset }: ResultPanelProps) {
  const { tl } = useLanguage();
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const savePath = await selectSaveLocation(result.nbs_file_name);
      if (savePath) {
        await copyFile(result.output_path, savePath);
      }
    } catch (e) {
      console.error('Save failed:', e);
    } finally {
      setSaving(false);
    }
  };

  const handleShowInFolder = async () => {
    try {
      await showInFolder(result.output_path);
    } catch (e) {
      console.error('Show in folder failed:', e);
    }
  };

  const handleCopyPath = async () => {
    try {
      await navigator.clipboard.writeText(result.output_path);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard may not be available in some webviews */
    }
  };

  const stats = [
    { icon: Music, label: tl(TRANSLATIONS.result.notes), value: result.note_count.toLocaleString() },
    { icon: Gauge, label: tl(TRANSLATIONS.result.bpm), value: Math.round(result.tempo).toString() },
    { icon: Layers, label: tl(TRANSLATIONS.result.layers), value: result.layer_count.toString() },
    { icon: Clock, label: tl(TRANSLATIONS.result.ticks), value: result.total_ticks.toLocaleString() },
    { icon: Clock, label: tl(TRANSLATIONS.result.range), value: 'F#1~F#7' },
  ];

  return (
    <Card className="border-green-200 bg-green-50/30">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-green-600" />
          <CardTitle className="text-base text-green-800">
            {tl(TRANSLATIONS.result.title)}
          </CardTitle>
        </div>
        <p className="text-xs text-muted-foreground mt-1 truncate">
          {result.nbs_file_name}
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid grid-cols-5 gap-2">
          {stats.map((stat) => (
            <div key={stat.label}
              className="flex flex-col items-center rounded-md border bg-white p-2">
              <stat.icon className="h-4 w-4 text-muted-foreground mb-1" />
              <span className="text-xs text-muted-foreground">{stat.label}</span>
              <span className="text-sm font-semibold">{stat.value}</span>
            </div>
          ))}
        </div>
        <Separator />
      </CardContent>

      <CardFooter className="flex flex-wrap gap-2">
        <Button onClick={handleSave} disabled={saving} size="sm">
          <Save className="h-4 w-4" />
          {tl(TRANSLATIONS.result.saveNbs)}
        </Button>
        <Button variant="secondary" onClick={handleShowInFolder} size="sm">
          <FolderOpen className="h-4 w-4" />
          {tl(TRANSLATIONS.result.showInFolder)}
        </Button>
        {onExportNbt && (
          <Button variant="outline" onClick={onExportNbt} size="sm">
            <FileOutput className="h-4 w-4" />
            {tl(TRANSLATIONS.result.exportNbt)}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={handleCopyPath}>
          {copied ? (
            <><Check className="h-4 w-4 text-green-600" />{tl(TRANSLATIONS.result.copied)}</>
          ) : (
            <><Copy className="h-4 w-4" />{tl(TRANSLATIONS.result.copyPath)}</>
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}
