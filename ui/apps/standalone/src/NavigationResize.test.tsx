// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { NavigationResize, navigationBounds } from "./NavigationResize";
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it("bounds width to keep the main area usable",()=>{
 expect(navigationBounds(1440,240,420,480)).toEqual({min:240,max:420});
 expect(navigationBounds(800,240,420,480)).toEqual({min:240,max:320});
});
it("supports keyboard bounds/reset, collapse restoration, and shrink clamp",()=>{
 let available=1440;
 vi.spyOn(HTMLElement.prototype,'clientWidth','get').mockImplementation(()=>available);
 const app=render(<div><button className="workspace-nav-toggle">toggle</button><NavigationResize enabled/></div>);
 const handle=screen.getByRole('separator');
 expect(handle).toHaveAttribute('aria-valuenow','288');
 fireEvent.keyDown(handle,{key:'End'});expect(handle).toHaveAttribute('aria-valuenow','420');
 app.rerender(<div><button className="workspace-nav-toggle">toggle</button><NavigationResize enabled={false}/></div>);
 expect(screen.queryByRole('separator')).not.toBeInTheDocument();
 app.rerender(<div><button className="workspace-nav-toggle">toggle</button><NavigationResize enabled/></div>);
 expect(handle).toHaveAttribute('aria-valuenow','420');
 available=800;fireEvent(window,new Event('resize'));expect(handle).toHaveAttribute('aria-valuenow','320');
 available=1440;fireEvent(window,new Event('resize'));expect(handle).toHaveAttribute('aria-valuenow','420');
 fireEvent.keyDown(handle,{key:'Home'});expect(handle).toHaveAttribute('aria-valuenow','240');
 fireEvent.keyDown(handle,{key:'ArrowRight'});expect(handle).toHaveAttribute('aria-valuenow','256');
 fireEvent.keyDown(handle,{key:'Enter'});expect(handle).toHaveAttribute('aria-valuenow','288');
});
