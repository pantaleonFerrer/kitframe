"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/hooks/use-i18n";
import { FieldInput, FieldLabel, FieldSelect, SettingsSection } from "../_components/ui";

type Member = {
  membership_id: string;
  user_id: string;
  email: string;
  name: string;
  role: string;
  can_approve_golden_set: boolean;
  last_login_at?: string | null;
};

type Invitation = {
  id: string;
  email: string;
  role: string;
  expires_at: string;
};

const ROLES = ["owner", "admin", "editor", "member", "viewer"];

export default function UsuariosPage() {
  const { te } = useI18n();
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [message, setMessage] = useState<string | null>(null);
  const [inviteToken, setInviteToken] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, i] = await Promise.all([
        api<{ data: Member[] }>("/members"),
        api<{ data: Invitation[] }>("/invitations").catch(() => ({ data: [] as Invitation[] })),
      ]);
      setMembers(m.data);
      setInvites(i.data);
      setError(null);
    } catch (e) {
      setError((e as Error).message || "Sin permiso o error de carga");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error) {
    return (
      <div className="bg-danger-subtle text-danger rounded-lg p-4 space-y-2">
        <p>{error}</p>
        <button type="button" className="underline text-sm" onClick={() => void load()}>
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold">Usuarios</h2>
        <p className="text-sm text-muted mt-1">Miembros de la marca e invitaciones pendientes.</p>
      </div>

      <SettingsSection title="Miembros">
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted border-b border-border">
                <th className="py-2 pr-2">Nombre</th>
                <th className="py-2 pr-2">Email</th>
                <th className="py-2 pr-2">Rol</th>
                <th className="py-2 pr-2">Golden set</th>
                <th className="py-2 pr-2">Último acceso</th>
                <th className="py-2"> </th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.membership_id} className="border-b border-border/60">
                  <td className="py-2 pr-2">{m.name}</td>
                  <td className="py-2 pr-2">{m.email}</td>
                  <td className="py-2 pr-2">
                    <FieldSelect
                      value={m.role}
                      onChange={async (e) => {
                        await api(`/members/${m.membership_id}`, {
                          method: "PATCH",
                          body: JSON.stringify({ role: e.target.value }),
                        });
                        await load();
                      }}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {te("roles", r)}
                        </option>
                      ))}
                    </FieldSelect>
                  </td>
                  <td className="py-2 pr-2">
                    <input
                      type="checkbox"
                      checked={m.can_approve_golden_set}
                      onChange={async (e) => {
                        await api(`/members/${m.membership_id}`, {
                          method: "PATCH",
                          body: JSON.stringify({ can_approve_golden_set: e.target.checked }),
                        });
                        await load();
                      }}
                    />
                  </td>
                  <td className="py-2 pr-2 text-xs text-muted">
                    {m.last_login_at ? new Date(m.last_login_at).toLocaleString() : "—"}
                  </td>
                  <td className="py-2">
                    <button
                      type="button"
                      className="text-xs text-danger"
                      onClick={async () => {
                        if (!confirm(`¿Quitar a ${m.email}?`)) return;
                        try {
                          await api(`/members/${m.membership_id}`, { method: "DELETE" });
                          await load();
                        } catch (e) {
                          setMessage((e as Error).message);
                        }
                      }}
                    >
                      Quitar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SettingsSection>

      <SettingsSection title="Invitar">
        <div className="grid md:grid-cols-3 gap-2 items-end">
          <FieldLabel>
            Email
            <FieldInput value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
          </FieldLabel>
          <FieldLabel>
            Rol
            <FieldSelect value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {te("roles", r)}
                </option>
              ))}
            </FieldSelect>
          </FieldLabel>
          <button
            type="button"
            className="rounded-md bg-wine text-white px-3 py-2 text-sm"
            onClick={async () => {
              try {
                const res = await api<{ id: string; token: string }>("/invitations", {
                  method: "POST",
                  body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
                });
                setInviteToken(res.token);
                setInviteEmail("");
                setMessage("Invitación creada");
                await load();
              } catch (e) {
                setMessage((e as Error).message);
              }
            }}
          >
            Invitar
          </button>
        </div>
        {inviteToken && (
          <p className="text-xs text-muted break-all">
            Enlace local: /invitacion/{inviteToken}
          </p>
        )}
        {message && <p className="text-xs text-wine">{message}</p>}
      </SettingsSection>

      <SettingsSection title="Invitaciones pendientes">
        {invites.length === 0 ? (
          <p className="text-sm text-muted">No hay invitaciones pendientes.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {invites.map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-2 border-b border-border/60 py-2">
                <span>
                  {i.email} · {te("roles", i.role)} · caduca{" "}
                  {new Date(i.expires_at).toLocaleDateString()}
                </span>
                <button
                  type="button"
                  className="text-xs text-danger"
                  onClick={async () => {
                    await api(`/invitations/${i.id}`, { method: "DELETE" });
                    await load();
                  }}
                >
                  Revocar
                </button>
              </li>
            ))}
          </ul>
        )}
      </SettingsSection>
    </div>
  );
}
