package domain

import "testing"

func TestValidTransitions(t *testing.T) {
	cases := []struct {
		from, to string
		ok       bool
	}{
		{StepTechnicalSheet, StepVisualProduction, true},
		{StepVisualProduction, StepRetouchQC, true},
		{StepRetouchQC, StepApproval, true},
		{StepApproval, StepPublished, true},
		{StepTechnicalSheet, StepRetouchQC, false},
		{StepTechnicalSheet, StepPublished, false},
		{StepApproval, StepVisualProduction, false},
		{StepPublished, StepApproval, false},
		{StepRetouchQC, StepVisualProduction, false},
	}
	for _, c := range cases {
		got := ValidTransition(c.from, c.to)
		if got != c.ok {
			t.Fatalf("%s -> %s: got %v want %v", c.from, c.to, got, c.ok)
		}
	}
}

func TestValidateAdvanceRequiresQC(t *testing.T) {
	err := ValidateAdvance(StepRetouchQC, StepApproval, AdvanceOptions{QCAllPass: false, AdminOverride: false})
	if err == nil {
		t.Fatal("expected qc required")
	}
	err = ValidateAdvance(StepRetouchQC, StepApproval, AdvanceOptions{QCAllPass: true})
	if err != nil {
		t.Fatalf("unexpected: %v", err)
	}
	err = ValidateAdvance(StepRetouchQC, StepApproval, AdvanceOptions{AdminOverride: true})
	if err != nil {
		t.Fatalf("unexpected override: %v", err)
	}
}

func TestValidateAdvancePublished(t *testing.T) {
	err := ValidateAdvance(StepApproval, StepPublished, AdvanceOptions{})
	if err != nil {
		t.Fatalf("unexpected: %v", err)
	}
	err = ValidateAdvance(StepRetouchQC, StepPublished, AdvanceOptions{})
	if err == nil {
		t.Fatal("expected invalid skip to published")
	}
}

func TestNextStep(t *testing.T) {
	n, ok := NextStep(StepTechnicalSheet)
	if !ok || n != StepVisualProduction {
		t.Fatalf("got %s %v", n, ok)
	}
	_, ok = NextStep(StepPublished)
	if ok {
		t.Fatal("published has no next")
	}
}
