import type { LanguageMeta } from './types';

/** All available languages with metadata */
export const LANGUAGES: LanguageMeta[] = [
  { code: 'zh', nativeName: '中文', englishName: 'Chinese' },
  { code: 'en', nativeName: 'English', englishName: 'English' },
];

// =============================================================================
// Translation dictionary — every UI string lives here
// =============================================================================

export const TRANSLATIONS = {
  // ---- Sidebar / App shell ------------------------------------------------
  app: {
    title: { zh: 'MP3 to NBS', en: 'MP3 to NBS' },
    version: { zh: 'v1.0.0', en: 'v1.0.0' },
    nav: {
      file: { zh: '文件', en: 'File' },
      nbt: { zh: 'NBT', en: 'NBT' },
      settings: { zh: '设置', en: 'Settings' },
    },
    envStatus: {
      checking: { zh: '检测中...', en: 'Checking...' },
      ready: { zh: '环境就绪', en: 'Environment ready' },
      incomplete: { zh: '环境不完整', en: 'Environment incomplete' },
      pythonMissing: { zh: '未检测到 Python', en: 'Python not detected' },
      packagesMissing: { zh: '个包缺失', en: 'packages missing' },
      recheck: { zh: '点击重新检测环境', en: 'Click to recheck environment' },
    },
  },

  // ---- Convert Page -------------------------------------------------------
  convert: {
    title: { zh: 'MP3 到 NBS 转换器', en: 'MP3 to NBS Converter' },
    description: {
      zh: '将音频文件转换为 Minecraft Note Block Studio 格式，支持自动音高检测、乐器映射和音源分离。',
      en: 'Convert audio files to Minecraft Note Block Studio format with automatic pitch detection, instrument mapping, and source separation.',
    },
    envWarning: {
      title: { zh: '环境未就绪', en: 'Environment not ready' },
      message: {
        zh: 'Python 或所需依赖包缺失。请在弹窗或设置页面完成环境配置。',
        en: 'Python or required packages are missing. Please complete the environment setup in the dialog or the Settings page.',
      },
    },
    conversionError: {
      title: { zh: '转换错误', en: 'Conversion Error' },
    },
    startButton: {
      zh: '开始转换',
      en: 'Start Conversion',
    },
    converting: {
      zh: '转换中...',
      en: 'Converting...',
    },
  },

  // ---- FileDropZone -------------------------------------------------------
  fileDrop: {
    prompt: {
      zh: '将音频文件拖放到此处，或',
      en: 'Drag & drop an audio file here, or ',
    },
    browse: {
      zh: '点击浏览',
      en: 'click to browse',
    },
    supported: {
      zh: '支持 MP3、WAV、FLAC、M4A、OGG 格式',
      en: 'Supports MP3, WAV, FLAC, M4A, OGG',
    },
  },

  // ---- ConversionOptions --------------------------------------------------
  options: {
    title: { zh: '转换选项', en: 'Conversion Options' },
    description: {
      zh: '配置转换流水线参数',
      en: 'Configure the conversion pipeline parameters',
    },
    sourceSeparation: {
      label: { zh: '音源分离', en: 'Source Separation' },
      description: {
        zh: '使用 Demucs + MDX-Net + Wiener 掩膜将音频分离为鼓、贝斯、人声和其他声部。大幅提高乐器映射准确度，但耗时更长。',
        en: 'Separate audio into drums, bass, vocals, and other stems using Demucs + MDX-Net + Wiener masks. Greatly improves instrument mapping accuracy but takes longer.',
      },
    },
    gpu: {
      label: { zh: 'GPU 加速', en: 'GPU Acceleration' },
      description: {
        zh: '使用 GPU 运行 Demucs 音源分离，速度可提升 5-10 倍。需要 NVIDIA GPU 并安装 CUDA 版 PyTorch。',
        en: 'Use GPU to run Demucs source separation — 5-10× faster. Requires an NVIDIA GPU with CUDA-enabled PyTorch.',
      },
      warning: {
        zh: '⚠️ 警告：如果显卡配置不足（显存 < 4GB 或非 NVIDIA 显卡），GPU 加速可能导致程序崩溃或运行失败。不确定的话请保持关闭。',
        en: '⚠️ Warning: GPU acceleration may crash or fail if your GPU is insufficient (< 4GB VRAM or non-NVIDIA GPU). Leave off if unsure.',
      },
    },
  },

  // ---- ProgressPanel ------------------------------------------------------
  progress: {
    converting: { zh: '转换中...', en: 'Converting...' },
    log: { zh: '处理日志', en: 'Processing Log' },
    steps: {
      loading: { zh: '加载音频', en: 'Loading Audio' },
      source_separation: { zh: '音源分离', en: 'Source Separation' },
      beat_tracking: { zh: '节拍检测', en: 'Beat Tracking' },
      pitch_detection: { zh: '音高检测', en: 'Pitch Detection' },
      generating_nbs: { zh: 'NBS 生成', en: 'NBS Generation' },
      complete: { zh: '完成', en: 'Complete' },
    },
  },

  // ---- ResultPanel --------------------------------------------------------
  result: {
    title: { zh: '转换完成', en: 'Conversion Complete' },
    notes: { zh: '音符数', en: 'Notes' },
    bpm: { zh: 'BPM', en: 'BPM' },
    layers: { zh: '层数', en: 'Layers' },
    ticks: { zh: 'Ticks', en: 'Ticks' },
    range: { zh: '音域', en: 'Range' },
    saveNbs: { zh: '保存 NBS', en: 'Save NBS' },
    showInFolder: { zh: '打开文件夹', en: 'Show in Folder' },
    exportNbt: { zh: '导出 .nbt', en: 'Export to .nbt' },
    copyPath: { zh: '复制路径', en: 'Copy Path' },
    copied: { zh: '已复制', en: 'Copied' },
  },

  // ---- NBT Export Page ----------------------------------------------------
  nbtExport: {
    title: { zh: 'NBS 转 .nbt 导出', en: 'NBS to .nbt Export' },
    description: {
      zh: '将 Note Block Studio 文件导出为 Minecraft .nbt 结构文件，配合 Noteblocks++ 模组在游戏中使用。',
      en: 'Export a Note Block Studio file to a Minecraft .nbt structure for in-game placement with Noteblocks++.',
    },
    infoTitle: { zh: '操作步骤', en: 'How this works' },
    infoSteps: [
      {
        zh: '在「文件」标签页将音频转换为 NBS 格式',
        en: 'Convert your audio to NBS using the File tab',
      },
      {
        zh: '使用 OpenNBS（或其他 NBS 编辑器）打开并编辑 .nbs 文件，微调音符、乐器和层',
        en: 'Open and edit the NBS file in OpenNBS (or another NBS editor) to fine-tune notes, instruments, and layers',
      },
      {
        zh: '回到此处选择你编辑好的 .nbs 文件',
        en: 'Come back here and select your edited .nbs file',
      },
      {
        zh: '导出为 .nbt 文件 — 配合 Noteblocks++ 模组即可在 Minecraft 中放置',
        en: 'Export as .nbt — ready to place in your Minecraft world with Noteblocks++ installed',
      },
    ],
    nbsFile: {
      title: { zh: 'NBS 文件', en: 'NBS File' },
      description: {
        zh: '选择要导出的 .nbs 文件',
        en: 'Select the .nbs file to export',
      },
      select: { zh: '选择 .nbs 文件', en: 'Select .nbs File' },
    },
    config: {
      title: { zh: '导出配置', en: 'Export Configuration' },
      description: {
        zh: '配置 .nbt 结构文件的生成方式',
        en: 'Configure how the .nbt structure is generated',
      },
    },
    spacing: {
      label: { zh: 'Tick 间距', en: 'Tick Spacing' },
      description: {
        zh: '每个 tick 之间沿 X 轴的方块数。数值越大，结构越分散。范围：1-4，默认：2。',
        en: 'Number of blocks between each tick along the X axis. Higher values spread the structure out more. Range: 1-4, default: 2.',
      },
    },
    dataVersion: {
      label: { zh: '数据版本 (DataVersion)', en: 'DataVersion' },
      description: {
        zh: 'Minecraft 数据版本号。3953 = 1.21，3465 = 1.20.4。如需适配其他版本请修改此项。',
        en: 'Minecraft data version number. 3953 = 1.21, 3465 = 1.20.4. Change this if you are targeting a different Minecraft version.',
      },
    },
    exportError: {
      title: { zh: '导出错误', en: 'Export Error' },
    },
    exportButton: {
      zh: '导出 .nbt',
      en: 'Export .nbt',
    },
    exporting: {
      zh: '导出中...',
      en: 'Exporting...',
    },
    exported: { zh: '已导出', en: 'Exported' },
    compatibilityNote: {
      zh: '重要提示：此导出需要安装 Noteblocks++ 模组（Fabric 或 Forge）以支持完整的 6 个八度音域。如果没有此模组，超出原版 2 个八度的音符将无法正常播放。生成的 .nbt 文件可通过 Minecraft 的结构方块加载，或通过 WorldEdit 示意图导入。',
      en: 'Important: This export requires the Noteblocks++ mod (Fabric or Forge) for full 6-octave note block support. Without this mod, notes outside the vanilla 2-octave range will not play correctly. The generated .nbt file can be loaded using a Structure Block in Minecraft, or imported via WorldEdit schematics.',
    },
  },

  // ---- Settings Page ------------------------------------------------------
  settings: {
    title: { zh: '设置', en: 'Settings' },
    description: {
      zh: '管理本地环境和导出配置。',
      en: 'Manage your local environment and export configuration.',
    },
    env: {
      title: { zh: '本地环境', en: 'Local Environment' },
      description: {
        zh: '音频处理所需的 Python 及依赖包状态',
        en: 'Python and required package status for audio processing',
      },
      python: {
        label: { zh: 'Python 3.11+', en: 'Python 3.11+' },
        notDetected: { zh: '未检测到', en: 'Not detected' },
        ready: { zh: '就绪', en: 'Ready' },
        missing: { zh: '缺失', en: 'Missing' },
      },
      packages: {
        label: { zh: '所需依赖包', en: 'Required Packages' },
        allReady: { zh: '所有依赖包就绪', en: 'All packages ready' },
      },
      overall: {
        ready: { zh: '所有依赖就绪', en: 'All dependencies ready' },
        missing: { zh: '依赖缺失', en: 'Dependencies missing' },
      },
      notChecked: {
        zh: '尚未检测环境状态。点击「重新检测」进行检测。',
        en: 'Environment status not yet checked. Click "Recheck" to detect.',
      },
      recheck: { zh: '重新检测', en: 'Recheck' },
      downloadPython: { zh: '下载 Python', en: 'Download Python' },
      installDeps: { zh: '安装缺失依赖', en: 'Install Missing Dependencies' },
    },
    conversion: {
      title: { zh: '转换默认值', en: 'Conversion Defaults' },
      description: {
        zh: '控制转换流水线的默认行为。这些设置可在转换页面按需覆盖。',
        en: 'Default conversion pipeline behaviour. These can be overridden per-conversion on the Convert page.',
      },
      gpuLabel: { zh: 'GPU 加速 (CUDA)', en: 'GPU Acceleration (CUDA)' },
      gpuDesc: {
        zh: '使用 NVIDIA GPU 运行 Demucs，速度可提升 5-10 倍。需安装 CUDA 版 PyTorch。',
        en: 'Use NVIDIA GPU to run Demucs — 5-10× faster. Requires CUDA-enabled PyTorch.',
      },
      gpuWarning: {
        zh: '⚠️ 显卡配置不足（显存 < 4GB 或非 NVIDIA）可能导致崩溃。不确定请关闭。',
        en: '⚠️ May crash if GPU is insufficient (< 4GB VRAM or non-NVIDIA). Leave off if unsure.',
      },
    },
    export: {
      title: { zh: '导出配置', en: 'Export Configuration' },
      description: {
        zh: '.nbt 结构文件导出的默认参数',
        en: 'Default parameters for .nbt structure file export',
      },
      spacingLabel: { zh: '.nbt 结构 Tick 间距', en: '.nbt Structure Tick Spacing' },
      spacingDesc: {
        zh: '控制生成结构中各 tick 之间的间距。每个 tick 沿 X 轴间隔一个中继器延迟。默认：2。',
        en: 'Controls the spacing between each tick in the generated structure. Each tick becomes one repeater delay apart along the X axis. Default: 2.',
      },
      dataVersionLabel: { zh: '数据版本 (DataVersion)', en: 'DataVersion' },
      dataVersionDesc: {
        zh: 'Minecraft 版本兼容值。默认 3953 对应 Minecraft 1.21。其他常用值：3465 (1.20.4)、3337 (1.20)、3120 (1.19.4)。',
        en: 'Minecraft version compatibility value. Default 3953 corresponds to Minecraft 1.21. Other common values: 3465 (1.20.4), 3337 (1.20), 3120 (1.19.4).',
      },
      note: {
        zh: '这些设置为 NBT 导出页面的默认值，可在导出时按需覆盖。',
        en: 'These settings are the defaults used when exporting on the NBT Export page. You can override them per-export from that page.',
      },
    },
  },

  // ---- EnvSetupModal ------------------------------------------------------
  envModal: {
    title: { zh: '环境配置', en: 'Environment Setup' },
    description: {
      zh: '运行转换需要以下依赖。',
      en: 'The following dependencies are needed to run conversions.',
    },
    pythonInstalled: { zh: '已安装', en: 'Installed' },
    pythonMissing: { zh: '缺失', en: 'Missing' },
    packagesAllReady: { zh: '所有依赖包就绪', en: 'All packages ready' },
    installing: { zh: '安装中...', en: 'Installing...' },
    installSuccess: { zh: '所有依赖包安装成功！', en: 'All packages installed successfully!' },
    installPartial: {
      zh: '部分依赖包未能安装',
      en: 'Some packages could not be installed',
    },
    installMissingButton: { zh: '安装缺失依赖', en: 'Install Missing Packages' },
    downloadPython: { zh: '下载 Python', en: 'Download Python' },
    skip: { zh: '暂时跳过', en: 'Skip for now' },
  },

  // ---- Language Switcher -------------------------------------------------
  lang: {
    label: { zh: '语言', en: 'Language' },
    switchTo: { zh: 'Switch to English', en: '切换到中文' },
  },
} as const;

// =============================================================================
// Helper: extract the translation function type
// =============================================================================

/** Top-level keys of the translation dictionary */
export type TranslationSection = keyof typeof TRANSLATIONS;

/**
 * Access a translation leaf by dotted path.
 * Example: `t('app.nav.file')` or `t('convert.startButton')`.
 *
 * Falls back to the key itself when the path is not found.
 */
export function t(path: string, lang: 'zh' | 'en'): string {
  const parts = path.split('.');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let node: any = TRANSLATIONS;

  for (const part of parts) {
    if (node == null || typeof node !== 'object') break;
    if (part in node) {
      node = node[part];
    } else {
      return path; // fallback
    }
  }

  if (node && typeof node === 'object' && lang in node) {
    return String(node[lang]);
  }

  return path; // fallback
}

/**
 * Type-safe translation lookup.
 * T is the shape of the leaf (typically `{ zh: string; en: string }`).
 */
export type TranslationLeaf = { zh: string; en: string };
