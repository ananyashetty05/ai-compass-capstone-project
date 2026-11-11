import { forwardRef } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { LinkProps } from 'react-router-dom';
import { cn } from '../../utils/cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'subtle' | 'danger' | 'danger-ghost' | 'link';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonCommonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  /** Renders a spinner and marks the control busy for assistive tech. */
  loading?: boolean;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export type ButtonProps = ButtonCommonProps & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'className'>;
export type ButtonLinkProps = ButtonCommonProps & Omit<LinkProps, 'children' | 'className'>;

function ButtonContent({ loading, leadingIcon, trailingIcon, children }: ButtonCommonProps) {
  return (
    <>
      {loading ? <span className="spinner" aria-hidden="true" /> : null}
      {!loading && leadingIcon ? (
        <span aria-hidden="true" className="btn-icon">
          {leadingIcon}
        </span>
      ) : null}
      {children}
      {!loading && trailingIcon ? (
        <span aria-hidden="true" className="btn-icon">
          {trailingIcon}
        </span>
      ) : null}
    </>
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', block, loading, leadingIcon, trailingIcon, children, className, disabled, type, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? 'button'}
      className={cn('btn', className)}
      data-variant={variant}
      data-size={size}
      data-block={block ? 'true' : undefined}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      <ButtonContent loading={loading} leadingIcon={leadingIcon} trailingIcon={trailingIcon} size={size}>
        {children}
      </ButtonContent>
    </button>
  );
});

/** Same visual language as Button, but renders a router link. */
export function ButtonLink({
  variant = 'secondary',
  size = 'md',
  block,
  leadingIcon,
  trailingIcon,
  children,
  className,
  ...rest
}: ButtonLinkProps) {
  return (
    <Link className={cn('btn', className)} data-variant={variant} data-size={size} data-block={block ? 'true' : undefined} {...rest}>
      <ButtonContent loading={false} leadingIcon={leadingIcon} trailingIcon={trailingIcon} size={size}>
        {children}
      </ButtonContent>
    </Link>
  );
}

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'aria-label' | 'className'> {
  /** Required: icon-only controls must expose an accessible name. */
  label: string;
  variant?: 'ghost' | 'bordered';
  active?: boolean;
  icon: ReactNode;
  size?: 'sm' | 'md';
  className?: string;
}

/** Icon-only button. `label` becomes the accessible name — never omit it. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, variant = 'ghost', active, icon, size = 'md', className, type, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? 'button'}
      className={cn('icon-btn', className)}
      data-variant={variant}
      data-size={size === 'md' ? undefined : size}
      data-active={active || undefined}
      aria-label={label}
      title={label}
      {...rest}
    >
      <span aria-hidden="true" className="icon-btn__icon">
        {icon}
      </span>
    </button>
  );
});

