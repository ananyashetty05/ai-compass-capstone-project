/**
 * Reusable UI primitives.
 *
 * Import from `@/components/ui` (or this barrel) rather than reaching
 * into individual files, so the surface stays explicit.
 */
export { Badge, ProvenanceTag, Status, Tag, TagList } from './Badge';
export type { BadgeProps, BadgeTone, ProvenanceKind, ProvenanceTagProps, StatusName, StatusProps, StatusTone } from './Badge';

export { Button, ButtonLink, IconButton } from './Button';
export type { ButtonProps, ButtonSize, ButtonVariant, ButtonLinkProps, IconButtonProps } from './Button';

export { Card, CardBody, CardFooter, CardHeader, StatCard } from './Card';
export type { CardProps, StatCardProps } from './Card';

export { Avatar, AvatarButton, CheckboxRow, SaveStateBar, SwitchRow } from './Controls';
export type { AvatarProps, SaveState } from './Controls';

export { DataTable } from './DataTable';
export type { ColumnDef, DataTableProps, SortDirection } from './DataTable';

export { EmptyState, ErrorState, Notice } from './EmptyState';
export type { EmptyStateProps, ErrorStateProps, NoticeProps, StateIconName } from './EmptyState';

export { Field, Select, TextArea, TextInput } from './Input';
export type { FieldProps, SelectProps, TextAreaProps, TextInputProps } from './Input';

export { MetricGrid, MetricTile } from './MetricTile';
export type { MetricGridProps, MetricTileProps } from './MetricTile';

export { Modal } from './Modal';
export type { ModalProps } from './Modal';

export { BandIndicator, DimensionRow, ScoreBar } from './ScoreBar';
export type { DimensionRowProps, ScoreBarProps } from './ScoreBar';

export { LoadingIndicator, Segmented, Skeleton, SkeletonBlock, SkeletonCard, SkeletonMetric, SkeletonMetrics, SkeletonTable } from './Skeleton';
export type { SegmentedOption, SkeletonProps } from './Skeleton';

export { AppLoading, Spinner } from './Spinner';

export { Slider } from './Slider';
export type { SliderProps } from './Slider';

export { InfoHint, Tooltip } from './Tooltip';
export type { TooltipPlacement, TooltipProps } from './Tooltip';

export { Toast } from './Toast';
