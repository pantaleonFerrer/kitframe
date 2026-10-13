package domain

import "github.com/gathered/kitframe/apps/api/internal/apperr"

const (
	StepTechnicalSheet   = "technical_sheet"
	StepVisualProduction = "visual_production"
	StepRetouchQC        = "retouch_qc"
	StepApproval         = "approval"
	StepPublished        = "published"
)

var stepOrder = []string{
	StepTechnicalSheet,
	StepVisualProduction,
	StepRetouchQC,
	StepApproval,
	StepPublished,
}

func ValidTransition(from, to string) bool {
	for i := 0; i < len(stepOrder)-1; i++ {
		if stepOrder[i] == from && stepOrder[i+1] == to {
			return true
		}
	}
	return false
}

func NextStep(from string) (string, bool) {
	for i := 0; i < len(stepOrder)-1; i++ {
		if stepOrder[i] == from {
			return stepOrder[i+1], true
		}
	}
	return "", false
}

type AdvanceOptions struct {
	QCAllPass      bool
	AdminOverride  bool
	TargetOverride string
}

func ValidateAdvance(from, to string, opts AdvanceOptions) error {
	if to == "" {
		var ok bool
		to, ok = NextStep(from)
		if !ok {
			return apperr.InvalidStepTransition(from, to)
		}
	}
	if !ValidTransition(from, to) {
		return apperr.InvalidStepTransition(from, to)
	}
	if to == StepApproval && !opts.QCAllPass && !opts.AdminOverride {
		return apperr.QCRequired()
	}
	return nil
}

func ResolveTarget(from, requested string) (string, error) {
	if requested == "" {
		next, ok := NextStep(from)
		if !ok {
			return "", apperr.InvalidStepTransition(from, requested)
		}
		return next, nil
	}
	if !ValidTransition(from, requested) {
		return "", apperr.InvalidStepTransition(from, requested)
	}
	return requested, nil
}
