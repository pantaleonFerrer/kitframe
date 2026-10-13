package permissions

type Role string

const (
	RoleViewer Role = "viewer"
	RoleEditor Role = "editor"
	RoleAdmin  Role = "admin"
	RoleOwner  Role = "owner"
)

type Permission string

const (
	PermViewBoard           Permission = "board.view"
	PermViewProduct         Permission = "product.view"
	PermEditStructuredData  Permission = "product.edit_structured_data"
	PermAdvanceStep         Permission = "product.advance_step"
	PermRunQC               Permission = "qc.run"
	PermApproveQC           Permission = "qc.approve"
	PermOverrideQC          Permission = "qc.override"
	PermPublishShopify      Permission = "shopify.publish"
	PermManageGoldenSet     Permission = "golden_set.manage"
	PermManageRights        Permission = "rights.manage"
	PermManageUsers         Permission = "users.manage"
	PermManageBrandSettings Permission = "brand.manage_settings"
)

var matrix = map[Role]map[Permission]bool{
	RoleViewer: {
		PermViewBoard:   true,
		PermViewProduct: true,
	},
	RoleEditor: {
		PermViewBoard:          true,
		PermViewProduct:        true,
		PermEditStructuredData: true,
		PermAdvanceStep:        true,
		PermRunQC:              true,
	},
	RoleAdmin: {
		PermViewBoard:          true,
		PermViewProduct:        true,
		PermEditStructuredData: true,
		PermAdvanceStep:        true,
		PermRunQC:              true,
		PermApproveQC:          true,
		PermOverrideQC:         true,
		PermPublishShopify:     true,
		PermManageGoldenSet:    true,
		PermManageRights:       true,
	},
	RoleOwner: {
		PermViewBoard:           true,
		PermViewProduct:         true,
		PermEditStructuredData:  true,
		PermAdvanceStep:         true,
		PermRunQC:               true,
		PermApproveQC:           true,
		PermOverrideQC:          true,
		PermPublishShopify:      true,
		PermManageGoldenSet:     true,
		PermManageRights:        true,
		PermManageUsers:         true,
		PermManageBrandSettings: true,
	},
}

func Has(role Role, perm Permission) bool {
	perms, ok := matrix[role]
	if !ok {
		return false
	}
	return perms[perm]
}

func RequiresOwnTeam(perm Permission) bool {
	return perm == PermEditStructuredData || perm == PermAdvanceStep
}

func CanActOnTeam(role Role, perm Permission, userTeam, resourceTeam string) bool {
	if !Has(role, perm) {
		return false
	}
	if role == RoleAdmin || role == RoleOwner {
		return true
	}
	if !RequiresOwnTeam(perm) {
		return true
	}
	if resourceTeam == "" {
		return true
	}
	return userTeam == resourceTeam
}

func AllPermissions() []Permission {
	return []Permission{
		PermViewBoard,
		PermViewProduct,
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
	}
}

func AllRoles() []Role {
	return []Role{RoleViewer, RoleEditor, RoleAdmin, RoleOwner}
}
