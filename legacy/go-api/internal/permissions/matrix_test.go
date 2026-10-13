package permissions

import "testing"

func TestViewerPermissions(t *testing.T) {
	if !Has(RoleViewer, PermViewBoard) {
		t.Fatal("viewer should view board")
	}
	if !Has(RoleViewer, PermViewProduct) {
		t.Fatal("viewer should view product")
	}
	if Has(RoleViewer, PermEditStructuredData) {
		t.Fatal("viewer must not edit")
	}
	if Has(RoleViewer, PermAdvanceStep) {
		t.Fatal("viewer must not advance")
	}
	if Has(RoleViewer, PermRunQC) {
		t.Fatal("viewer must not run qc")
	}
	if Has(RoleViewer, PermApproveQC) {
		t.Fatal("viewer must not approve qc")
	}
	if Has(RoleViewer, PermPublishShopify) {
		t.Fatal("viewer must not publish")
	}
	if Has(RoleViewer, PermManageGoldenSet) {
		t.Fatal("viewer must not manage golden set")
	}
	if Has(RoleViewer, PermManageRights) {
		t.Fatal("viewer must not manage rights")
	}
	if Has(RoleViewer, PermManageUsers) {
		t.Fatal("viewer must not manage users")
	}
	if Has(RoleViewer, PermManageBrandSettings) {
		t.Fatal("viewer must not manage brand")
	}
}

func TestEditorPermissions(t *testing.T) {
	if !Has(RoleEditor, PermEditStructuredData) {
		t.Fatal("editor should edit structured data")
	}
	if !Has(RoleEditor, PermAdvanceStep) {
		t.Fatal("editor should advance step")
	}
	if !Has(RoleEditor, PermRunQC) {
		t.Fatal("editor should run qc")
	}
	if Has(RoleEditor, PermApproveQC) {
		t.Fatal("editor must not approve qc")
	}
	if Has(RoleEditor, PermOverrideQC) {
		t.Fatal("editor must not override qc")
	}
	if Has(RoleEditor, PermPublishShopify) {
		t.Fatal("editor must not publish")
	}
	if Has(RoleEditor, PermManageUsers) {
		t.Fatal("editor must not manage users")
	}
}

func TestAdminPermissions(t *testing.T) {
	if !Has(RoleAdmin, PermApproveQC) {
		t.Fatal("admin should approve qc")
	}
	if !Has(RoleAdmin, PermOverrideQC) {
		t.Fatal("admin should override qc")
	}
	if !Has(RoleAdmin, PermPublishShopify) {
		t.Fatal("admin should publish")
	}
	if !Has(RoleAdmin, PermManageGoldenSet) {
		t.Fatal("admin should manage golden set")
	}
	if !Has(RoleAdmin, PermManageRights) {
		t.Fatal("admin should manage rights")
	}
	if Has(RoleAdmin, PermManageUsers) {
		t.Fatal("admin must not manage users")
	}
	if Has(RoleAdmin, PermManageBrandSettings) {
		t.Fatal("admin must not manage brand settings")
	}
}

func TestOwnerPermissions(t *testing.T) {
	for _, p := range AllPermissions() {
		if !Has(RoleOwner, p) {
			t.Fatalf("owner missing permission %s", p)
		}
	}
}

func TestEditorOwnTeamOnly(t *testing.T) {
	if !CanActOnTeam(RoleEditor, PermAdvanceStep, "creative", "creative") {
		t.Fatal("editor should act on own team")
	}
	if CanActOnTeam(RoleEditor, PermAdvanceStep, "creative", "ecommerce") {
		t.Fatal("editor must not act on other team")
	}
	if !CanActOnTeam(RoleAdmin, PermAdvanceStep, "creative", "ecommerce") {
		t.Fatal("admin should act across teams")
	}
	if !CanActOnTeam(RoleOwner, PermEditStructuredData, "", "retail") {
		t.Fatal("owner should act across teams")
	}
}

func TestRBACMatrixNegativeCells(t *testing.T) {
	denied := map[Role][]Permission{
		RoleViewer: {
			PermEditStructuredData,
			PermAdvanceStep,
			PermRunQC,
			PermApproveQC,
			PermOverrideQC,
			PermPublishShopify,
			PermManageGoldenSet,
			PermManageRights,
			PermManageUsers,
			PermManageBrandSettings,
		},
		RoleEditor: {
			PermApproveQC,
			PermOverrideQC,
			PermPublishShopify,
			PermManageGoldenSet,
			PermManageRights,
			PermManageUsers,
			PermManageBrandSettings,
		},
		RoleAdmin: {
			PermManageUsers,
			PermManageBrandSettings,
		},
	}
	for role, perms := range denied {
		for _, p := range perms {
			if Has(role, p) {
				t.Fatalf("%s must not have %s", role, p)
			}
		}
	}
}

func TestViewerMustNotOverrideQC(t *testing.T) {
	if Has(RoleViewer, PermOverrideQC) {
		t.Fatal("viewer must not override qc")
	}
}

func TestEditorMustNotManageGoldenSetOrRightsOrBrand(t *testing.T) {
	if Has(RoleEditor, PermManageGoldenSet) {
		t.Fatal("editor must not manage golden set")
	}
	if Has(RoleEditor, PermManageRights) {
		t.Fatal("editor must not manage rights")
	}
	if Has(RoleEditor, PermManageBrandSettings) {
		t.Fatal("editor must not manage brand settings")
	}
}
